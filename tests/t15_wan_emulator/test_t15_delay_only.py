"""T15 — NTG chained through the WAN emulator: delay only.

From the 2026-09-30 meeting: extend the scripts to drive the WAN emulator
together with the traffic engine, starting with delay-only, and check that
the NTG reports the added latency correctly. Loss and other impairments
come after this works.

Wiring: NTG Port 3 <-> emulator Engine 2 <-> NTG Port 4 (wan_emulator.py).

The same UDP testbed runs twice:
  1. baseline — emulator untouched (Engine 2 bypass), read the NTG's
     "Avg latency" for the run;
  2. delayed — Engine 2 gets a delay-only path (DELAY_MS each way, access
     links wide open) for the length of the run, then is put back.
The run must still PASS (delay alone shouldn't drop frames), and the
NTG's average latency must rise by DELAY_MS within TOLERANCE_MS. The NTG
measures one-way latency per stream, so one direction's delay is the
expected rise, not the round trip.

500 Mbps per port: Port 4's link is ~1 Gbps (the emulator's own port 4
negotiated 1000 Mbps; see netropy-ui-findings.md).

Measured numbers go into the run history via the run_metrics fixture
(docs/wan-integration-plan.md step 2): for each run, the NTG's saved run
(read through its API) and Engine 2's counters for the path the traffic
took, with per-second series of both in the sidecar file. The frame
accounting checks (emulator frames per direction vs NTG frames sent that
way) are recorded but not enforced yet, because one direction carried only ~1/10
of the frames on 2026-10-05 and that's still under investigation.

Stateful: generates real traffic and reconfigures the shared emulator.
"""
import re

import pytest
from playwright.sync_api import Page, expect

import wan_emulator
from ntg_api import NtgApi
from run_metrics import ntg_run_digest
from wan_api import WanApi
from conftest import (
    add_stream,
    assert_activatable_name,
    assert_run_passed,
    create_testbed,
    enable_ports,
    go_to_dashboard,
    open_editor,
    remove_testbed,
    set_addressing,
    set_all_frame_sizes,
    set_ramp,
    start_testbed,
    testbed_tile,
    wait_for_run_to_finish,
)

TESTBED_NAME = "T15-WAN-Delay"
assert_activatable_name(TESTBED_NAME)
PATH_NAME = "t15-ntg-delay"
PORTS = ["Port 3", "Port 4"]
DELAY_MS = 50
TOLERANCE_MS = 5
# Frame accounting tolerance: ARP and other control frames also cross the
# emulator, so allow 0.5 % of the frames sent.
FRAME_TOLERANCE = 0.005

_AVG_LATENCY = re.compile(r"([\d,]+(?:\.\d+)?)\s*ms")


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


def _run_once(page: Page):
    """Build the UDP testbed, run it to completion, return its saved row."""
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)
    enable_ports(page, PORTS, rate="500", unit="Mbps")
    set_addressing(page, (3, 4), ("10.0.0.1", "10.0.0.2"), cidr=25)
    add_stream(page, "UDP")
    set_all_frame_sizes(page, 1500)
    set_ramp(page, up=2, hold=20, down=2)
    start_testbed(page)
    return wait_for_run_to_finish(page, timeout=24_000 + 3 * 60_000)


def _latest_avg_latency_ms(page: Page) -> float:
    """The latest saved run's "Avg Latency" card (e.g. "Avg Latency 0.224 ms")
    on the testbed's Stats page, behind its "Last run #N" button."""
    go_to_dashboard(page)
    testbed_tile(page, TESTBED_NAME).get_by_role("button", name="Stats").click()
    page.get_by_role("button", name=re.compile(r"^Last run #")).click()
    card = page.get_by_role("button", name="Avg Latency: open graph")
    expect(card).to_contain_text(_AVG_LATENCY, timeout=20_000)
    return float(_AVG_LATENCY.search(card.inner_text()).group(1).replace(",", ""))


def _wan_delta(before: dict, after: dict) -> dict:
    """Counter growth per direction between two WanApi.flows() reads
    (numbers subtracted, nested dicts recursed, the rest taken from after)."""
    def diff(a, b):
        if isinstance(b, dict):
            return {k: diff((a or {}).get(k), v) for k, v in b.items()}
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) and not isinstance(b, bool):
            return b - a
        return b
    return {key[1]: diff(before.get(key), flow) for key, flow in after.items()}


def _measured_run(label, page, ntg, wan, path_label, run_metrics):
    """_run_once() with both boxes' numbers recorded around it. Returns the
    saved Test Reports row and the NTG run digest."""
    index = wan.path_index(wan_emulator.ENGINE_INDEX, path_label)
    before = wan.flows(wan_emulator.ENGINE_INDEX, [index])
    seq_start = wan.stats_summary(wan_emulator.ENGINE_INDEX, [index])["current"]
    row = _run_once(page)
    after = wan.flows(wan_emulator.ENGINE_INDEX, [index])
    seq_end = wan.stats_summary(wan_emulator.ENGINE_INDEX, [index])["current"]

    saved = ntg.run(TESTBED_NAME, ntg.latest_run(TESTBED_NAME)["run-id"])
    config = ntg.test(TESTBED_NAME)
    digest = ntg_run_digest(saved)
    digest["configured-ports"] = [
        {k: p.get(k) for k in ("port-id", "rate-mbps", "speed-mbps")} for p in config.get("port", [])
    ]
    engine = wan.engine(wan_emulator.ENGINE_INDEX)
    run_metrics.add_run(
        label,
        ntg=digest,
        wan={
            "engine": wan_emulator.ENGINE_INDEX,
            "path": path_label,
            "path-index": index,
            "delta": _wan_delta(before, after),
            "buffers": engine["status"]["buffers"],
            "seq": [seq_start, seq_end],
        },
        series={
            "ntg": saved.get("sample"),
            "wan": _wan_series(wan, index, seq_start, seq_end),
            "ntg-config": config,
        },
    )
    _check_tx_rates(label, digest, run_metrics)
    _check_frame_accounting(label, digest, run_metrics.record["runs"][-1]["wan"]["delta"], run_metrics)
    return row, digest


def _wan_series(wan, index, start, end):
    """Per-second emulator records for the run. Best-effort: charts are
    nice to have and must never fail the test."""
    try:
        return wan.stats_records(wan_emulator.ENGINE_INDEX, [index], start=start, end=end).get("data")
    except Exception as exc:
        return {"error": str(exc)}


def _check_tx_rates(label, digest, run_metrics):
    """Each port's whole-run average TX vs its configured rate. The 2 s
    ramps pull the average a few % under; 15 % allows for that. Recorded,
    not enforced: on .212 Port 4 sends ~1/10 of its rate (2026-10-05) and
    that's a suspected product bug to report, not something to fail T15 on."""
    actual = {p["port-id"]: p.get("avg-tx-rate") for p in digest["port"]}
    for port in digest["configured-ports"]:
        rate = port.get("rate-mbps")
        if rate:
            run_metrics.check(
                f"{label}: NTG Port {port['port-id']} avg TX = configured rate",
                expected=rate,
                measured=actual.get(port["port-id"]),
                tolerance=rate * 0.15,
                unit="Mbps",
                enforced=False,
            )


def _check_frame_accounting(label, digest, wan_delta, run_metrics):
    """Emulator frames per direction vs NTG frames sent that way. The NTG
    reports raw (0-based) port ids; the lower one is Port 3, and emulator
    a-to-b is its port 3 -> 4, so a-to-b should match NTG Port 3 -> 4."""
    sent = {}
    for d in digest["direction"]:
        key = (d["from-port"], d["to-port"])
        sent[key] = sent.get(key, 0) + d.get("tx-frames", 0)
    if len(sent) != 2:
        return
    low_to_high, high_to_low = sorted(sent, key=lambda k: k[0])
    for direction, ntg_key, name in (
        ("a-to-b", low_to_high, "Port 3→4"),
        ("b-to-a", high_to_low, "Port 4→3"),
    ):
        expected = sent[ntg_key]
        run_metrics.check(
            f"{label}: emulator {direction} frames = NTG {name} frames sent",
            expected=expected,
            measured=(wan_delta.get(direction) or {}).get("frames"),
            tolerance=expected * FRAME_TOLERANCE,
            unit="frames",
            enforced=False,
        )


@pytest.mark.stateful
def test_t15_delay_only_adds_expected_latency(
    dashboard: Page, wan_page: Page, clean_testbed, run_metrics
):
    page = dashboard
    ntg, wan = NtgApi.from_env(), WanApi.from_env()
    run_metrics.set_impairment({
        "engine": wan_emulator.ENGINE_INDEX,
        "path": PATH_NAME,
        "a-to-b": {"delay": f"constant {DELAY_MS} ms"},
        "b-to-a": {"delay": f"constant {DELAY_MS} ms"},
    })

    row, base_run = _measured_run("baseline", page, ntg, wan, "Bypass", run_metrics)
    assert_run_passed(row)
    baseline = _latest_avg_latency_ms(page)
    remove_testbed(page, TESTBED_NAME)

    with wan_emulator.delay_between_ntg_ports(wan_page, PATH_NAME, DELAY_MS):
        go_to_dashboard(page)
        row, delayed_run = _measured_run("delayed", page, ntg, wan, PATH_NAME, run_metrics)
    assert_run_passed(row)
    delayed = _latest_avg_latency_ms(page)

    # The UI's card and the API's saved run should be the same number (µs -> ms).
    for label, ui, run in (("baseline", baseline, base_run), ("delayed", delayed, delayed_run)):
        run_metrics.check(
            f"{label}: Avg Latency card = API avg-latency",
            expected=ui,
            measured=run["summary"]["avg-latency"] / 1000,
            tolerance=0.001,
            unit="ms",
            enforced=False,
        )
    added = delayed - baseline
    ok = run_metrics.check(
        "avg latency added by the emulator",
        expected=DELAY_MS,
        measured=round(added, 3),
        tolerance=TOLERANCE_MS,
        unit="ms",
    )
    assert ok, (
        f"emulator added {DELAY_MS} ms each way, but NTG avg latency went "
        f"{baseline:.3f} -> {delayed:.3f} ms (+{added:.3f} ms)"
    )

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

Stateful: generates real traffic and reconfigures the shared emulator.
"""
import re

import pytest
from playwright.sync_api import Page, expect

import wan_emulator
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


@pytest.mark.stateful
def test_t15_delay_only_adds_expected_latency(
    dashboard: Page, wan_page: Page, clean_testbed, record_property
):
    page = dashboard

    assert_run_passed(_run_once(page))
    baseline = _latest_avg_latency_ms(page)
    remove_testbed(page, TESTBED_NAME)

    with wan_emulator.delay_between_ntg_ports(wan_page, PATH_NAME, DELAY_MS):
        go_to_dashboard(page)
        run = _run_once(page)
    assert_run_passed(run)
    delayed = _latest_avg_latency_ms(page)

    added = delayed - baseline
    record_property("baseline_avg_latency_ms", baseline)
    record_property("delayed_avg_latency_ms", delayed)
    assert abs(added - DELAY_MS) <= TOLERANCE_MS, (
        f"emulator added {DELAY_MS} ms each way, but NTG avg latency went "
        f"{baseline:.3f} -> {delayed:.3f} ms (+{added:.3f} ms)"
    )

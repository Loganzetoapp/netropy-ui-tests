"""T14 — 64-byte frames across protocols: does any of them put the unit
in a bad state?

Source: Joe's email of 2026-09-30, after testing Vlad's new 5.0 build:
"When you create TCP and HTTP streams that have 64-byte frames it puts
the system in a bad state (UDP streams are ok at 64 bytes). Let's add a
TC(s) that test a variety of streams with different protocols using
64-byte frames." He also asked engineering for something to poll at the
end of a TC that says the system is in a bad state, so those can be
marked as system failures in the test reports.

What each case does, on Port 3 <-> Port 4 (the only cabled pair on the
5.0 unit at .89), 500 Mbps per port (under Port 4's ~1 Gbps link), one
stream, 64-byte frames, 2/15/2 s ramp:
  1. checks the unit is healthy before starting;
  2. builds and starts the testbed and waits for the run to be saved;
  3. checks the unit is still healthy afterwards.

"Healthy" is read from the UI only (this suite never calls the API; see
conftest.assert_unit_healthy): the top bar must say "online" with no
"offline" / "controller offline" / "RECOVERY" indicator, no testbed may be
"disconnected", and the run must actually be saved (a run that ends with
no saved record is the engineer's "stats lost" case). An unhealthy unit
raises SystemBadStateError, which the reports show as a SYSTEM failure,
distinct from an ordinary FAIL.

Order matters: UDP first as the control the email says is fine, then
other protocols, and the two the email names (TCP, HTTP) last, so a bad
state they cause can't make earlier cases look broken. Once the unit is
found unhealthy, every later case is skipped with that reason instead of
failing for it. A run that loses its results on a still-healthy unit is
reported as a system failure for that case only (seen for DNS at 64 B on
2026-10-01, and for NTP at 90 B in the T10 lifecycle tests). The canary (a plain UDP run) always runs and tells
you whether the unit recovered on its own. It's the last case of the same
parametrized test (a separate test or file gets reordered ahead of the
sweep by pytest's parametrize grouping).

These cases are expected to FAIL for TCP and HTTP until the bug is fixed.
That's the point — they are not xfail-ed, so the failure stays visible.
Recovering the unit after a bad state may need a manual reboot; nothing
here tries to recover it.

Stateful: generates real traffic, and may leave the unit unusable.
Never run without the user explicitly asking (CLAUDE.md).
"""
import pytest
from playwright.sync_api import Page

from conftest import (
    SystemBadStateError,
    add_stream,
    assert_activatable_name,
    assert_unit_healthy,
    create_testbed,
    enable_ports,
    open_editor,
    remove_testbed,
    run_verdict,
    set_all_frame_sizes,
    set_ramp,
    start_testbed,
    wait_for_run_to_finish,
)

PORTS = ["Port 3", "Port 4"]
RATE_MBPS = "500"
FRAME_BYTES = 64

# (Add Stream picker label, testbed name, frame bytes). Safe-by-report
# first; the two protocols the email names last; then the canary — plain
# UDP at 1500 B — which always runs, to show whether the unit recovered.
CANARY = ("UDP", "T14-Canary", 1500)
CASES = [
    ("UDP", "T14-64B-UDP", FRAME_BYTES),
    ("ICMP", "T14-64B-ICMP", FRAME_BYTES),
    ("ARP", "T14-64B-ARP", FRAME_BYTES),
    ("DNS", "T14-64B-DNS", FRAME_BYTES),
    ("UDP (IPv6)", "T14-64B-UDP6", FRAME_BYTES),
    ("TCP (IPv6)", "T14-64B-TCP6", FRAME_BYTES),
    ("TCP", "T14-64B-TCP", FRAME_BYTES),
    ("HTTP", "T14-64B-HTTP", FRAME_BYTES),
    CANARY,
]
CASE_IDS = [
    "canary-UDP-1500B" if c is CANARY else c[0].replace(" (", "-").rstrip(")") for c in CASES
]
for _, _name, _ in CASES:
    assert_activatable_name(_name)

# First system failure seen in this module: {"test": nodeid, "reason": str}.
_unit_broken: dict = {}


def _record_if_system_failure(request, exc: BaseException) -> None:
    """Remember the first time the UNIT was found unhealthy, so later cases
    skip instead of failing for it. A lost run on a still-healthy unit is
    reported as a system failure but does not stop the sweep."""
    if (
        isinstance(exc, SystemBadStateError)
        and str(exc).startswith("Unit unhealthy")
        and not _unit_broken
    ):
        _unit_broken.update(test=request.node.name, reason=str(exc))


def _teardown(page: Page, name: str) -> None:
    """Remove the testbed. If the unit is already known to be broken, a
    failed cleanup is expected and only reported, not raised — it would
    otherwise bury the real (system) failure under a teardown error."""
    try:
        remove_testbed(page, name)
    except Exception as exc:
        if _unit_broken:
            print(f"[T14] cleanup of {name} failed on an unhealthy unit: {exc}")
        else:
            raise


def _run_case(page: Page, request, protocol: str, name: str, frame: int) -> None:
    try:
        assert_unit_healthy(page, context=f"before {protocol} {frame}B")
        create_testbed(page, name)
        open_editor(page, name)
        enable_ports(page, PORTS, rate=RATE_MBPS, unit="Mbps")
        add_stream(page, protocol)
        set_all_frame_sizes(page, frame)
        set_ramp(page, up=2, hold=15, down=2)
        try:
            start_testbed(page)
            run = wait_for_run_to_finish(page, timeout=19_000 + 3 * 60_000)
        except SystemBadStateError:
            # A lost run is a system failure for this case. Only stop the
            # rest of the sweep if the unit itself is now unhealthy — on
            # 2026-10-01 a DNS run lost its stats while the unit stayed fine.
            assert_unit_healthy(page, context=f"after {protocol} {frame}B lost its run")
            raise
        except Exception as exc:
            # A start or run that goes wrong: decide whether the unit itself
            # is now unhealthy (system failure) or this was an ordinary failure.
            assert_unit_healthy(page, context=f"after {protocol} {frame}B start/run failed: {exc}")
            raise
        # Read the saved run before the health check navigates away from it.
        verdict, row_text = run_verdict(run), run.inner_text()
        print(f"[T14] {protocol} {frame}B saved run: {row_text!r}")
        assert_unit_healthy(page, context=f"after {protocol} {frame}B run")
        assert verdict == "pass", f"run verdict {verdict!r}; saved run row: {row_text!r}"
    except BaseException as exc:
        _record_if_system_failure(request, exc)
        raise


@pytest.fixture
def case_testbed(dashboard: Page, request):
    case = request.node.callspec.params["case"]
    name = case[1]
    if _unit_broken and case is not CANARY:
        pytest.skip(
            f"Unit already unhealthy after {_unit_broken['test']}: {_unit_broken['reason']}"
        )
    _teardown(dashboard, name)
    yield name
    _teardown(dashboard, name)


@pytest.mark.stateful
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_t14_64b_frames_leave_unit_healthy(dashboard: Page, case_testbed, case, request):
    protocol, name, frame = case
    _run_case(dashboard, request, protocol, name, frame)

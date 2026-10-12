"""T10/T12 combined lifecycle test — TCP variant.

Sibling of test_t10_t12_lifecycle_udp_1gbps_1500b.py with different
parameters: TCP instead of UDP, 2 Gbps instead of 1, 512-byte frames
instead of 1500, Port 5 + Port 6 instead of Port 3 + Port 4, and a
shorter ramp (5/30/5 = 40s instead of 10/50/10 = 70s).

Creates a Traffic Engine testbed on Port 5 + Port 6, configures a single
TCP stream at 2 Gbps line rate with 512-byte frames, activates it, waits
for the run to finish on its own, and asserts the result is PASS — then
cleans up (release ports, delete testbed).

Stateful: generates real traffic on shared hardware.

Selector note: several wizard controls (frame size input, ramp inputs,
network config fields, the subnet-mask <select>) have no accessible name,
role, or data-testid, so this falls back to CSS position (`.fc`, `.seg`,
`nth-child`) recorded via Playwright codegen. Flagging per the "report UI
issues" convention — these controls, plus testbed tiles (`div.tb-tile`,
no ARIA role at all) and icon-only action buttons (download/duplicate/
delete with no aria-label/title), would benefit from data-testid
attributes; noting here for the PR description rather than silently
working around it.

NTG 5.0 rewrite (2026-09-30): the 4.0 flow this was recorded against
(manual Reserve, "Available" port status, Apply -> Deactivate -> Start,
CSS-position selectors into the Network cards) no longer exists. The test
now drives the same configuration through the shared role-based helpers
in conftest.py and starts via Start -> "Testbed is Inactive" -> Continue,
which reserves and activates the ports itself. Selector caveats above
about `.fc`/`.seg`/`nth-child` no longer apply.
"""
import pytest
from playwright.sync_api import Page

from conftest import (
    add_stream,
    assert_activatable_name,
    create_testbed,
    enable_ports,
    open_editor,
    remove_testbed,
    assert_run_passed,
    set_addressing,
    set_all_frame_sizes,
    set_ramp,
    start_testbed,
    wait_for_run_to_finish,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-Life-TCP"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 5", "Port 6"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_tcp_2gbps_512b(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="2", unit="Gbps")
    set_addressing(page, (5, 6), ("10.0.1.1", "10.0.1.2"), cidr=25)
    add_stream(page, "TCP")
    set_all_frame_sizes(page, 512)
    set_ramp(page, up=5, hold=30, down=5)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=40 * 1000 + 3 * 60_000)

    assert_run_passed(run)

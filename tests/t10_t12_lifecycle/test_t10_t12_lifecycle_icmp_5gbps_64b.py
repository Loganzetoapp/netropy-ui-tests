"""T10/T12 combined lifecycle test — ICMP variant.

Sibling of test_t10_t12_lifecycle_udp_1gbps_1500b.py and
test_t10_t12_lifecycle_tcp_2gbps_512b.py with different parameters: ICMP
instead of UDP/TCP, 5 Gbps line rate, 64-byte (minimum Ethernet) frames,
Port 1 + Port 2 instead of Port 3+4 / 5+6, a /26 subnet instead of /25
(62 hosts instead of 126 — the CIDR select only offers /25-/32, so /24
isn't an option) on a distinct IP range, and an 8/45/8 = 61s ramp.

Creates a Traffic Engine testbed on Port 1 + Port 2, configures a single
ICMP stream at 5 Gbps line rate with 64-byte frames, activates it, waits
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
TESTBED_NAME = "T10-Life-ICMP"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_icmp_5gbps_64b(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="5", unit="Gbps")
    set_addressing(page, (1, 2), ("10.0.2.1", "10.0.2.2"), cidr=26)
    add_stream(page, "ICMP")
    set_all_frame_sizes(page, 64)
    set_ramp(page, up=8, hold=45, down=8)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=61 * 1000 + 3 * 60_000)

    assert_run_passed(run)

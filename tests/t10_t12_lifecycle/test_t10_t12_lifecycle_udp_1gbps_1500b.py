"""T10/T12 combined lifecycle test.

Creates a Traffic Engine testbed on Port 3 + Port 4, configures a single
UDP stream at 1 Gbps line rate with 1500-byte frames, 10.0.0.1/25 <-> 10.0.0.2/25
addressing and a 10/50/10 s ramp, starts it (NTG 5.0: Start -> "Testbed is Inactive" -> Continue),
waits for the run to finish on its own, and asserts the saved result is
PASS. Teardown deactivates (releasing the ports) and deletes the testbed.

Stateful: generates real traffic.

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
TESTBED_NAME = "T10-Life-UDP"
assert_activatable_name(TESTBED_NAME)
PORTS = ['Port 3', 'Port 4']


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_udp_1gbps_1500b(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="1", unit="Gbps")
    set_addressing(page, (3, 4), ("10.0.0.1", "10.0.0.2"), cidr=25)
    add_stream(page, "UDP")
    set_all_frame_sizes(page, 1500)
    set_ramp(page, up=10, hold=50, down=10)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=70 * 1000 + 3 * 60_000)

    assert_run_passed(run)

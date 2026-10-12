"""T10/T12 combined lifecycle test — multi-stream (TCP + ICMP), no UDP.

Sibling of the single-stream UDP/TCP/ICMP lifecycle tests, but exercises
a wizard path none of them cover: a testbed with *two streams on one
testbed* (TCP + ICMP together), rather than one stream per testbed.
Deliberately excludes UDP — every other lifecycle test in this suite
already uses it as its sole stream, so this one specifically covers the
"multiple non-UDP protocols coexisting" combination.

Creates a Traffic Engine testbed on Port 3 + Port 4, adds a TCP stream
(900-byte frames) and an ICMP stream (100-byte frames) to the same
testbed, activates it, waits for the run to finish on its own, and
asserts the result is PASS — then cleans up (release ports, delete
testbed).

Stateful: generates real traffic on shared hardware.

Port note (2026-08-26): Port 3+4 are reused here (already exercised by
the single-stream UDP sibling) because Port 5-8 are all currently
Down/No Link — see project_bugs_found memory. Switch back to an unused
pair once those recover, if a fully disjoint set becomes preferable.

Selector note: same caveats as the single-stream siblings — several
wizard controls have no accessible name/role/data-testid and fall back
to CSS position (`.fc`, `.seg`, `nth-child`). The frame-size input is
additionally indexed per stream row here (`.nth(i)` instead of
`.first`), since with two streams there are two such inputs on the page.

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
    set_ramp,
    set_stream_frame_size,
    start_testbed,
    wait_for_run_to_finish,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-Life-Multi"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="3", unit="Gbps")
    set_addressing(page, (3, 4), ("10.0.6.1", "10.0.6.2"), cidr=27)
    add_stream(page, "TCP")
    add_stream(page, "ICMP")
    set_stream_frame_size(page, 0, 900)
    set_stream_frame_size(page, 1, 100)
    set_ramp(page, up=5, hold=25, down=5)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=35 * 1000 + 3 * 60_000)

    assert_run_passed(run)

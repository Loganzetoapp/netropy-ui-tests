"""T10/T12 combined lifecycle test — NTP variant.

Sibling of the UDP/TCP/ICMP lifecycle tests, using a protocol from the
wizard's "Application" category instead of the generic IPv4 ones.

Protocol research (via the live "✚ Add Stream" picker before writing this
test — see project_bugs_found memory, 2026-09-10): NTP's picker entry
reads "Time sync, UDP port 123", layer stack Ethernet → IPv4 → UDP →
Payload, "Default ports: 123 → 123" (symmetric — real NTP clients and
servers both use port 123), and creates exactly one stream ("ntp") per
Add — same 1-stream-per-testbed shape as every other single-protocol
lifecycle sibling.

Line rate/frame size are deliberately realistic for the protocol: real
NTP traffic is tiny, infrequent sync packets (~48-90 bytes on the wire),
not sustained bulk transfer — nowhere near this suite's multi-gigabit
siblings — so this uses 50 Mbps (line-rate unit dropdown switched to
Mbps, not a fractional Gbps value) and 90-byte frames (a real NTP packet
plus Ethernet/IP/UDP headers, at the upper end of a typical NTP payload).

Creates a Traffic Engine testbed on Port 3 + Port 4, configures a single
NTP stream, activates it, waits for the run to finish on its own, and
asserts the result is PASS — then cleans up (release ports, delete
testbed).

Stateful: generates real traffic on the box.

Selector note: same caveats as every sibling — several wizard controls
have no accessible name/role/data-testid and fall back to CSS position
(`.fc`, `.seg`, `nth-child`).

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
TESTBED_NAME = "T10-Life-NTP"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_ntp_50mbps_90b(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="50", unit="Mbps")
    set_addressing(page, (3, 4), ("10.0.8.1", "10.0.8.2"), cidr=29)
    add_stream(page, "NTP")
    set_all_frame_sizes(page, 90)
    set_ramp(page, up=4, hold=20, down=4)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=28 * 1000 + 3 * 60_000)

    assert_run_passed(run)

"""T10/T12 combined lifecycle test — DNS variant.

Sibling of the UDP/TCP/ICMP lifecycle tests, using a protocol from the
wizard's "Application" category instead of the generic IPv4 ones.

Protocol research (via the live "✚ Add Stream" picker before writing this
test — see project_bugs_found memory, 2026-09-10): DNS's picker entry
reads "Name lookups, UDP port 53", layer stack Ethernet → IPv4 → UDP →
Payload, "Default ports: 2048 → 53", and creates exactly one stream
("dns") per Add — same 1-stream-per-testbed shape as every other
single-protocol lifecycle sibling, just with the destination port
pre-set to 53 instead of UDP's generic 2048. No extra per-stream port
editing needed after picking the protocol.

Confirmed live (not just from the picker's description) that DNS isn't
its own layer: the created stream's layer chips read Ethernet/IPv4/UDP/
Payload, same as the plain UDP sibling — there's no separate "DNS" chip
to wait on, only "UDP".

Line rate/frame size are deliberately realistic for the protocol rather
than reusing the siblings' multi-gigabit values: real DNS traffic is
small queries/responses, not sustained bulk transfer, so this uses 200
Mbps (switching the line-rate unit dropdown, not a fractional Gbps
value) and 128-byte frames (a typical query/response with EDNS
overhead — bigger than a bare 12-byte DNS header, far short of a full
1500-byte frame).

Creates a Traffic Engine testbed on Port 1 + Port 2, configures a single
DNS stream, activates it, waits for the run to finish on its own, and
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
TESTBED_NAME = "T10-Life-DNS"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_dns_200mbps_128b(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="200", unit="Mbps")
    set_addressing(page, (1, 2), ("10.0.7.1", "10.0.7.2"), cidr=28)
    add_stream(page, "DNS")
    set_all_frame_sizes(page, 128)
    set_ramp(page, up=6, hold=35, down=6)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=47 * 1000 + 3 * 60_000)

    assert_run_passed(run)

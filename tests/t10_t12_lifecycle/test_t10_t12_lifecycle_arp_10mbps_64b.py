"""T10/T12 combined lifecycle test — ARP variant.

Sibling of the UDP/TCP/ICMP lifecycle tests, using a Layer 2 protocol
instead of anything IP-based — the first lifecycle test in this suite
that isn't UDP/TCP/ICMP-shaped.

Protocol research (via the live "✚ Add Stream" picker before writing this
test — see project_bugs_found memory, 2026-09-10): ARP's picker entry
reads "Address resolution frames", layer stack **Ethernet → Payload only**
— no IPv4/UDP/TCP layer at all, and no "Default ports" line (there's
nothing to have a port). Creates exactly one stream ("arp") per Add,
same 1-stream shape as every other single-protocol sibling.

**Network Configuration deliberately left at its auto-filled defaults**
here, unlike every IP-based sibling which sets custom static IPs: since
ARP has no IP layer, per-port source/destination IP addressing isn't
meaningful for what the stream actually sends on the wire. Confirmed by
exploration that the wizard's step 2 still renders the full IP/MAC form
regardless of protocol (it's generic to the testbed, not stream-aware),
so this is a deliberate choice to leave it alone, not an oversight.

Frame size is pinned to 64 bytes, the Ethernet minimum, matching a real
(non-padded) ARP frame's actual size on the wire more closely than a
larger value would. Line rate is a modest 10 Mbps — real ARP traffic is
inherently bursty address-resolution lookups, not sustained bulk load,
so this is the lowest rate among this suite's lifecycle siblings.

Creates a Traffic Engine testbed on Port 3 + Port 4, configures a single
ARP stream, activates it, waits for the run to finish on its own, and
asserts the result is PASS — then cleans up (release ports, delete
testbed).

Port note (2026-09-10): originally written against Port 5+6, and passed
cleanly there once — but 5/6 went Down/No Link again right after (the
same recurring hardware issue documented in project_bugs_found memory,
not caused by this test), so this was switched to Port 3+4 to keep the
suite immediately runnable. Switch back once 5/6 are confirmed healthy
again, if a fully disjoint port set becomes preferable.

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
    set_all_frame_sizes,
    set_ramp,
    start_testbed,
    wait_for_run_to_finish,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-Life-ARP"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 3", "Port 4"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_t12_lifecycle_arp_10mbps_64b(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)

    enable_ports(page, PORTS, rate="10", unit="Mbps")
    add_stream(page, "ARP")
    set_all_frame_sizes(page, 64)
    set_ramp(page, up=3, hold=15, down=3)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=21 * 1000 + 3 * 60_000)

    assert_run_passed(run)

"""T10 — two testbeds running simultaneously on disjoint ports.

Explicitly called out in the plan's T10 section ("Two testbeds running
simultaneously on disjoint ports") but not yet covered by the single-
testbed lifecycle siblings (UDP on Port 3+4, TCP on Port 5+6, ICMP on
Port 1+2). This test builds and activates a UDP testbed on Port 1+2 and
a TCP testbed on Port 3+4, confirms both are live (Stop visible) at the
same time, waits for both to finish naturally, and asserts both PASS
independently — proving the product genuinely runs concurrent testbeds
rather than serializing them under the hood.

Port pair note (2026-08-26): originally used Port 3+4 / Port 7+8, but
Port 7+8 went Down/No Link after their first-ever activation while
developing this test — same symptom as the Port 5/6 incident on
2026-08-25 (see project_bugs_found memory), both times on a pair's
*first* activation. At Logan's direction, using only Port 1-4 (both
already exercised cleanly by the ICMP/UDP siblings) until 5-8 are
confirmed healthy again.

UI update (2026-09-17): this test used to build+Apply (configure +
activate, no traffic) both testbeds first, waiting at the Deactivate bar,
then Start both back-to-back — that two-step gap was what let both be
staged before either generated traffic, guaranteeing overlap regardless
of how long testbed B took to build. See
test_t10_t12_lifecycle_multistream_udp_tcp_100mbps.py for the full
writeup: Apply and Start have been merged into a single "Start" action
that activates AND starts traffic together, so there is no more way to
stage a testbed at "activated but idle" — clicking Start on testbed A
immediately starts its traffic, before testbed B has even been built.

To keep genuine overlap under this constraint, testbed A is now given a
deliberately long hold phase (15/180/15 = 210s) — comfortably longer than
the ~90s the original sequencing-bug writeup measured for building a
second testbed through the wizard — so A is still guaranteed to be live
when testbed B's own Start (build immediately followed by Start) fires.
B keeps a shorter 15/60/15 = 90s ramp. This is a best-effort adaptation
of the original design's intent (assert genuine concurrent runs, not a
coincidental near-miss) rather than a re-validated timing measurement —
see NEEDS HUMAN REVIEW below.

An earlier version of this test (pre-dating even the Apply/Start merge)
built+started A, then built B while A ran, with too-short a ramp on A;
A's short ramp finished before B's ~90s of wizard setup was even done,
so they never actually overlapped — sequencing bug, not a selector
issue. That same failure mode is exactly what the long A hold above
guards against, now structurally required rather than optional.

The wizard-filling steps happen sequentially in this script (Playwright
drives one page at a time), same as a human would. The actual
concurrency being verified is server-side — both testbeds' runs
overlapping in time — not simultaneous UI actions.

Stateful: generates real traffic on shared hardware, on two testbeds at
once. Never run alongside the other T10/T12 lifecycle tests (no xdist,
no parallel stateful runs, per CLAUDE.md) — this test's own two port
pairs are disjoint from each other, but it should still run alone
relative to other stateful tests.

Selector note: same caveats as the single-testbed siblings — several
wizard controls have no accessible name/role/data-testid and fall back
to CSS position (`.fc`, `.seg`, `nth-child`). See those files' docstrings
for the full rationale; not repeated here.

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec

TESTBED_A_NAME = "T10-Concur-A"
TESTBED_B_NAME = "T10-Concur-B"
# A's long hold keeps it live while B is built and started.
SPEC_A = TestbedSpec(ports={1: PortSpec(rate=1), 2: PortSpec(rate=1)},
                     streams=[StreamSpec("UDP")], frame_size=1500, ramp=(15, 180, 15))
SPEC_B = TestbedSpec(ports={3: PortSpec(rate=1), 4: PortSpec(rate=1)},
                     streams=[StreamSpec("TCP")], frame_size=1500, ramp=(15, 60, 15))


@pytest.mark.stateful
def test_t10_two_testbeds_run_simultaneously(dashboard: Page, traffic_engine):
    board = traffic_engine.dashboard
    traffic_engine.create(TESTBED_A_NAME, SPEC_A)
    traffic_engine.start(TESTBED_A_NAME)
    traffic_engine.create(TESTBED_B_NAME, SPEC_B)
    traffic_engine.start(TESTBED_B_NAME)

    # Both live at the same moment: genuine overlap, not serialized.
    board.open()
    expect(board.is_running(TESTBED_A_NAME)).to_be_visible(timeout=15_000)
    expect(board.is_running(TESTBED_B_NAME)).to_be_visible(timeout=15_000)

    for name, spec, label in ((TESTBED_B_NAME, SPEC_B, "B (TCP, 3/4)"),
                              (TESTBED_A_NAME, SPEC_A, "A (UDP, 1/2)")):
        board.open()
        expect(board.is_running(name)).to_have_count(0, timeout=spec.run_seconds * 1000 + 120_000)
        board.tile_button(name, "Stats").click()
        row = traffic_engine.runs.wait_for_run_to_finish(1, timeout=60_000)
        traffic_engine.result(name, row, label=label, expected_seconds=spec.run_seconds).assert_passed()

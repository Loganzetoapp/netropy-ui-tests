"""T10 — port conflict while a testbed is actively using it.

Exploratory test, not a happy-path regression. The plan's T10 section
covers *disjoint* concurrent testbeds (see test_t10_two_testbeds_simultaneous.py
— Testbed A on Port 1+2, Testbed B on Port 3+4, verified to genuinely
overlap). It never covers the inverse: what happens if a *second* testbed
tries to claim ports a *first*, currently-live testbed is already using.
That's the gap this test hunts in.

Port note (2026-09-15): only Port 3 + Port 4 are confirmed safe to use
right now (a late constraint from Logan, after Port 1/2 were originally
planned for this test — see git history of this file). So, unlike most
lifecycle siblings, there's no separate disjoint "control" pair available
here — and none is actually needed: the conflict only requires one
testbed's ports to be attempted twice. Testbed A gets Port 3 + Port 4,
real and live; Testbed B then attempts to claim that *exact same pair*
while A is still running. A pre/post snapshot of Port 3's own dashboard
row (captured before anything reserves it, then again once A holds it)
stands in for the cross-port "known available" comparison other tests in
this file would normally use.

Scenario: build, Apply, and Start Testbed A on Port 3 + Port 4 — real
traffic, actually running. While A is live, open a second testbed's
(Testbed B) wizard and, on its Ports step, attempt to also enable Port 3
and Port 4 — exactly the pair A is actively using.

Expected/correct behavior (asserted): the product should not let Testbed
B silently claim ports a live testbed is already using. That could
reasonably show up as — the ports' rows/toggles in B's Ports step
reading as unavailable and refusing to toggle on; the dashboard row
showing something other than "Available" while A holds them; or, at
worst, an explicit, visible block/error if the wizard lets the toggle
proceed but Apply is where the conflict is actually caught. What would
NOT be acceptable: B's toggles turning on with no signal at all, Apply
silently succeeding with both testbeds now claiming the same ports, or
Testbed A's live run breaking/disappearing as a side effect of B's
attempt.

This mirrors the two-testbed sibling's builder/starter helpers
(_reserve_ports / _release_ports / _delete_testbed_if_present /
_build_and_apply_testbed / _start_testbed) rather than reinventing them —
see that file's docstring for the concurrency-timing rationale behind
building+Applying before Starting, and for the CSS-position selector
caveats shared by every wizard step in this suite.

Stateful: generates real traffic on shared hardware. Never run alongside
other T10/T12 lifecycle tests (no xdist, no parallel stateful runs, per
CLAUDE.md).

--- What was actually observed (2026-09-15, one run against 192.168.173.111) ---
Testbed A (UDP, Port 3+4, 1 Gbps, 10/180/10s ramp) built, Applied, and
Started cleanly — confirmed live (Stop visible on its tile) before any
conflict probing began.

Dashboard-level signal (non-destructive read): Port 3's row went from
"...Available...Reserve" (captured before this test reserved anything)
to "...Reserved / test (you) / T10-Conflict-A / Release" once A held it
— a clear, correctly-attributed ownership change.

Wizard-level signal (Testbed B's own Ports step): Port 3's row read
"⚠ in use by testbed \"T10-Conflict-A\"" — and so did Port 4's. So the
product DOES surface, by name, exactly which testbed already holds a
port, right in the Ports-step table of a second testbed being built.

However — the toggle switches for both Port 3 and Port 4 were NOT
disabled. Clicking them turned them on exactly as a free port's toggle
would (their "line rate" fields became visible and fillable), with no
confirm dialog, no blocking tooltip, nothing to stop selection beyond the
informational warning text already sitting right there in the same row.
Filling in both ports' config and finishing the rest of Testbed B's
wizard (network config, one UDP stream, traffic/load profile) and
clicking Apply: the call did NOT silently succeed — Testbed B never
reached an activated state (no "Deactivate" bar appeared within 30s), and
Testbed A was reconfirmed live and unaffected afterward (its Stop button
was visible again via a proper `expect()` wait by the end of the test;
see selector note below on why an intermediate plain `.is_visible()`
snapshot briefly, spuriously, read False).

Verdict: **not a silent-acceptance bug.** The product ultimately blocks
the conflicting activation and never corrupts Testbed A's running state
— the invariant this test actually guards on (no silent conflict, no
corrupted live testbed) held, so the test passes. But it's a genuine,
worth-flagging UX gap: the Ports step already has the exact information
needed ("⚠ in use by testbed \"T10-Conflict-A\"") rendered right on the
row, but doesn't use it to disable the toggle or block selection before
Apply — a user only finds out the port is unavailable after configuring
an entire second testbed end-to-end and clicking Apply at the very end,
with no visible-in-this-run indication of *why* it didn't activate (no
toast/error text was seen in this run's UI at the point Apply silently
failed to transition — only the absence of the expected "Deactivate"
button gave it away). That absence-of-explicit-error is itself a repeat
of the same UX gap already logged in netropy-ui-findings.md ("The
frontend shows nothing when activation fails") — this test reproduces
that same silence for a *different* underlying cause (port conflict, not
the 15-char name limit). Reported to Logan per the "report UI issues"
convention rather than worked around; not asserted as a hard failure
here since the task's actual bar for a bug (silent *acceptance* of the
conflict, or corruption of A) was not met.

Selector note (this test's own imprecision, not a product bug): right
after Testbed B's failed Apply, a diagnostic-only `tile_a.get_by_role(
"button", name="Stop").is_visible()` (a single snapshot with no wait,
used only for a print statement) read False immediately after navigating
back to the dashboard — almost certainly because the dashboard's tile
list briefly re-renders on that navigation and the plain read raced it.
The test's actual final assertion re-checks the same locator through a
proper `expect(...).to_be_visible()` (auto-retrying up to the default 10s),
which passed — confirming A was genuinely still live throughout. Kept the
plain read in for its diagnostic print value but it should not be read as
evidence of real instability; same "don't trust an unwaited snapshot"
lesson as the UDP lifecycle sibling's own "BUG FOUND" note about racing
Start.

Hardware confirmed clean afterward: Port 3 and Port 4 back to
"Available", both testbeds deleted, no tiles left on the dashboard. Port
1 and Port 2 were never touched by this test at all — they were already
"Reserved" by pre-existing testbeds `ta-c1`/`ta-s2` (owner `admin`)
before this test ran, and are unchanged.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed names must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_A_NAME = "T10-Conflict-A"
TESTBED_B_NAME = "T10-Conflict-B"
assert_activatable_name(TESTBED_A_NAME)
assert_activatable_name(TESTBED_B_NAME)

# Only Port 3 + Port 4 are confirmed safe right now (see module docstring).
# Testbed B attempts to claim this exact same pair while A is live on it —
# there's no separate free/disjoint pair available or needed here.
PORTS = ["Port 3", "Port 4"]
BUFFER_MS = 400


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _port_number(port_label: str) -> int:
    return int(port_label.split()[-1])


def _testbed_tile(page: Page, name: str):
    return page.locator(".tb-tile").filter(has_text=name)


def _delete_testbed_if_present(page: Page, name: str):
    tile = _testbed_tile(page, name)
    if tile.count() > 0:
        # Icon order confirmed via screenshot: [0]=download [1]=duplicate [2]=delete
        tile.locator("button").nth(2).click()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(_testbed_tile(page, name)).to_have_count(0, timeout=10000)


def _release_ports(page: Page, ports):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        # A failure mid-wizard (before Apply/Save) leaves unsaved edits, so
        # navigating away pops an "Unsaved changes" confirm modal (Discard
        # / Save & close / Keep editing) that blocks the plain click above
        # from actually landing on the dashboard.
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)
    for port_label in ports:
        row = page.get_by_role("row", name=port_label)
        release_btn = row.get_by_role("button", name="Release")
        if release_btn.is_visible():
            release_btn.click()
            confirm = page.get_by_role("button", name="Deactivate & release")
            if confirm.is_visible():
                confirm.click()
            expect(row.get_by_text("Available", exact=True)).to_be_visible(timeout=10000)


@pytest.fixture
def clean_testbeds(dashboard: Page):
    _delete_testbed_if_present(dashboard, TESTBED_A_NAME)
    _delete_testbed_if_present(dashboard, TESTBED_B_NAME)
    yield
    # Release first (an active port's Release pops "Deactivate & release",
    # tearing down whichever testbed still holds it), then delete both
    # testbed objects — same order as the two-testbed sibling's teardown,
    # robust regardless of which branch of the conflict probe was hit.
    _release_ports(dashboard, PORTS)
    _delete_testbed_if_present(dashboard, TESTBED_A_NAME)
    _delete_testbed_if_present(dashboard, TESTBED_B_NAME)


def _reserve_ports(page: Page, ports):
    for port_label in ports:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)


def _build_and_apply_testbed(
    page: Page,
    *,
    name: str,
    ports,
    ip_base: str,
    cidr: str,
    rate_gbps: int,
    frame_size: int,
    ramp,
):
    """Build a UDP Traffic Engine testbed through the wizard and Apply
    (activate) it. Adapted from test_t10_two_testbeds_simultaneous.py's
    helper of the same name — trimmed to just the UDP path (the only
    protocol this test needs) since Testbed A here doesn't need protocol
    parameterization.
    """
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(name)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    _testbed_tile(page, name).get_by_role("button", name="Edit").click()
    _buffer(page)
    for port_label in ports:
        n = _port_number(port_label)
        page.locator(f"tr:nth-child({n}) > td > div > .toggle > .track").click()
        _buffer(page)
    for port_label in ports:
        rate_field = page.get_by_role(
            "row", name=re.compile(rf"^{re.escape(port_label)}\b")
        ).get_by_placeholder("line rate")
        rate_field.fill(str(rate_gbps))
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(rf"^{re.escape(ports[-1])}\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    ip1, ip2 = f"{ip_base}1", f"{ip_base}2"
    page.get_by_role("textbox", name="10.1.0.10").first.fill(ip1)
    _buffer(page)
    page.locator(".seg").first.select_option(cidr)
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill(ip2)
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option(cidr)
    _buffer(page)
    page.get_by_role("textbox", name="auto").nth(2).fill(ip1)
    _buffer(page)
    page.get_by_role("textbox", name="auto").first.fill(ip2)
    _buffer(page)

    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)

    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
    frame_size_field = page.locator("td:nth-child(5) > .fc").first
    frame_size_field.fill(str(frame_size))
    _buffer(page)
    frame_size_field.press("Enter")
    _buffer(page)

    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    up, hold, down = ramp
    page.locator(".fc > input").first.fill(str(up))
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill(str(hold))
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill(str(down))
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()


def _start_testbed(page: Page, name: str):
    """Click Start on an already-Applied testbed's dashboard tile — same
    as the two-testbed sibling's helper.
    """
    _testbed_tile(page, name).get_by_role("button", name="Start").click()
    _buffer(page)


@pytest.mark.stateful
def test_t10_port_conflict_while_active(dashboard: Page, clean_testbeds):
    page = dashboard

    # --- Baseline (non-destructive): Port 3's dashboard row before
    # anything reserves it, for later before/after comparison. ---
    port3_dash_row = page.get_by_role("row", name="Port 3")
    port3_baseline_text = port3_dash_row.inner_text()
    print(f"\n[conflict probe] Port 3 dashboard row BEFORE any reservation: {port3_baseline_text!r}")
    assert "Available" in port3_baseline_text, (
        "Sanity check failed: Port 3 should read 'Available' before this "
        f"test touches it. Actual row text: {port3_baseline_text!r}"
    )

    # --- Build, Apply, and Start Testbed A on Port 3+4 — real, live traffic ---
    # A generous 10/180/10s ramp gives plenty of time to run the conflict
    # probe below against a genuinely still-live testbed, without racing
    # A's own natural finish.
    _reserve_ports(page, PORTS)
    _build_and_apply_testbed(
        page,
        name=TESTBED_A_NAME,
        ports=PORTS,
        ip_base="10.0.6.",
        cidr="25",
        rate_gbps=1,
        frame_size=1000,
        ramp=(10, 180, 10),
    )
    _start_testbed(page, TESTBED_A_NAME)
    tile_a = _testbed_tile(page, TESTBED_A_NAME)
    expect(tile_a.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)

    # --- Probe 1 (non-destructive, dashboard-level): does the port table
    # reflect Port 3 as claimed now, vs. its own pre-reservation baseline? ---
    port3_live_text = port3_dash_row.inner_text()
    print(f"[conflict probe] Port 3 dashboard row while A is live: {port3_live_text!r}")
    assert "Available" not in port3_live_text, (
        "Port 3's dashboard row still reads 'Available' while Testbed "
        f"{TESTBED_A_NAME} is actively running on it — the dashboard is not "
        f"reflecting the port as in-use at all. Actual row text: {port3_live_text!r}"
    )
    assert port3_live_text != port3_baseline_text, (
        "Port 3's dashboard row is identical before reservation and while "
        f"{TESTBED_A_NAME} is live on it ({port3_live_text!r}) — no visible "
        "change at all to reflect the port now being claimed."
    )

    # --- Create Testbed B's draft and open its wizard on the Ports step ---
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(TESTBED_B_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)
    _testbed_tile(page, TESTBED_B_NAME).get_by_role("button", name="Edit").click()
    _buffer(page)

    # --- Probe 2 (wizard-level): read Port 3 and Port 4's rows inside B's
    # own Ports step, before touching either toggle. ---
    port3_wiz_row = page.get_by_role("row", name=re.compile(r"^Port 3\b"))
    port4_wiz_row = page.get_by_role("row", name=re.compile(r"^Port 4\b"))
    port3_wiz_text = port3_wiz_row.inner_text()
    port4_wiz_text = port4_wiz_row.inner_text()
    print(f"[conflict probe] Port 3 row in B's Ports step: {port3_wiz_text!r}")
    print(f"[conflict probe] Port 4 row in B's Ports step: {port4_wiz_text!r}")

    # --- Attempt to toggle both Port 3 and Port 4 on in Testbed B, exactly
    # as a user would if trying to (deliberately or accidentally) claim
    # the pair A is already using. ---
    toggles_blocked = {}
    for port_label in PORTS:
        n = _port_number(port_label)
        try:
            page.locator(f"tr:nth-child({n}) > td > div > .toggle > .track").click(timeout=5000)
            _buffer(page)
            toggles_blocked[port_label] = False
        except Exception as exc:
            toggles_blocked[port_label] = True
            print(f"[conflict probe] {port_label}'s toggle in B's wizard was not clickable: {exc}")

    port3_rate_field = port3_wiz_row.get_by_placeholder("line rate")
    port4_rate_field = port4_wiz_row.get_by_placeholder("line rate")

    def _became_selectable(field, port_label):
        return (
            not toggles_blocked[port_label]
            and field.count() > 0
            and field.is_visible()
            and field.is_enabled()
        )

    port3_became_selectable = _became_selectable(port3_rate_field, "Port 3")
    port4_became_selectable = _became_selectable(port4_rate_field, "Port 4")
    print(f"[conflict probe] Port 3 became selectable/fillable in B's wizard: {port3_became_selectable}")
    print(f"[conflict probe] Port 4 became selectable/fillable in B's wizard: {port4_became_selectable}")

    if not (port3_became_selectable or port4_became_selectable):
        # Best-case outcome: the wizard itself refuses to let a second
        # testbed select ports the live testbed already holds. Nothing
        # further to build — discard B's draft and confirm A is healthy.
        print("[conflict probe] Neither port's toggle activated while claimed by "
              f"{TESTBED_A_NAME} — conflict blocked at the earliest possible point.")
    else:
        # At least one toggle let it through. Finish configuring whichever
        # ports became selectable, then see whether Apply itself catches —
        # or fails to catch — the conflict.
        print("[conflict probe] WARNING: at least one port's toggle turned on in "
              f"Testbed B's wizard with no block, even though its own row(s) show "
              f"Port 3={port3_wiz_text!r} Port 4={port4_wiz_text!r} — proceeding to "
              "Apply to see whether the conflict is caught there instead.")
        if port3_became_selectable:
            port3_rate_field.fill("1")
            _buffer(page)
        if port4_became_selectable:
            port4_rate_field.fill("1")
            port4_rate_field.press("Enter")
            _buffer(page)

        page.get_by_role("button", name="2 Network Configuration per-").click()
        _buffer(page)
        page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.7.1")
        _buffer(page)
        page.locator(".seg").first.select_option("25")
        _buffer(page)
        page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("10.0.7.2")
        _buffer(page)
        page.locator(
            "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
            "> div > div:nth-child(2) > .ne-combo > select"
        ).select_option("25")
        _buffer(page)
        page.get_by_role("textbox", name="auto").nth(2).fill("10.0.7.1")
        _buffer(page)
        page.get_by_role("textbox", name="auto").first.fill("10.0.7.2")
        _buffer(page)

        page.get_by_role("button", name="3 Streams traffic flows — at").click()
        _buffer(page)
        page.get_by_role("button", name="✚ Add Stream").click()
        _buffer(page)
        add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
        if add_stream_btn.is_visible():
            add_stream_btn.click()
            _buffer(page)
        expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()
        frame_size_field = page.locator("td:nth-child(5) > .fc").first
        frame_size_field.fill("1000")
        _buffer(page)
        frame_size_field.press("Enter")
        _buffer(page)

        page.get_by_role("button", name="4 Traffic and Load Profile").click()
        _buffer(page)
        page.get_by_role("button", name="Apply", exact=True).click()
        _buffer(page)

        # Give this real room, same as a normal activate — but this is the
        # crux check: did Apply silently let live ports get double-claimed?
        b_activated = False
        try:
            expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=30000)
            b_activated = True
        except Exception:
            pass

        # Whatever happened to B, immediately re-check A wasn't corrupted.
        page.get_by_role("button", name="← Dashboard").click()
        _buffer(page)
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
        expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)

        a_still_live = tile_a.get_by_role("button", name="Stop").is_visible()
        print(f"[conflict probe] Testbed B reached an activated state on Apply: {b_activated}")
        print(f"[conflict probe] Testbed A still shows Stop (live/unharmed) after B's attempt: {a_still_live}")

        assert not b_activated, (
            f"BUG: Testbed {TESTBED_B_NAME} was allowed to Apply/activate "
            "with Port 3/4 selected while Testbed "
            f"{TESTBED_A_NAME} was actively, live using those same ports — "
            "the product silently let a second testbed claim in-use ports "
            f"instead of blocking it. Testbed A live afterward: {a_still_live}."
        )

    # --- Final sanity: Testbed A's run should still be genuinely healthy,
    # regardless of which branch above was taken ---
    expect(tile_a.get_by_role("button", name="Stop")).to_be_visible()

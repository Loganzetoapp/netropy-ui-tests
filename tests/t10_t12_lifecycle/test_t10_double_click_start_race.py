"""T10 — double-click race on Start (and, budget permitting, on a fresh
draft's very first Start click).

Last of a five-test exploratory batch hunting for real product bugs via
untried state-transition combinations. The other four already found: (1) a
port-conflict that fails silently with no visible error
(test_t10_port_conflict_while_active.py), (2) a confirmed cross-protocol
extension of the known VXLAN "Start doesn't really start" bug
(test_t10_cross_layer_multistream_arp_dns_vxlan.py), (3) graceful handling
of asymmetric subnet masks — no bug, but extends the known "no validation"
finding (test_t10_asymmetric_subnet_pairing.py), and (4) a NEW bug in
test_t10_rapid_stop_restart_cycle.py's close cousin,
test_t10_rapid_stop_restart_cycle... actually found in the sibling that
restarts Start on a just-Stopped (not deactivated) testbed: doing so can
cause the run to silently self-terminate after only ~2-4s instead of its
configured duration, with no error shown anywhere.

This test asks a different but adjacent question: what happens if a user's
mouse (or an impatient double-tap) sends a click-triggered control *two*
click events back to back, right at the moment it's about to arm/start a
testbed? Single-click Start (and single-click Continue on its confirmation
modal) is well-trodden ground (every other lifecycle test in this file uses
it) — the untried part is the *double*-click, which touches the same
state-transition territory as finding (4) above: does the frontend de-dupe
it (second click is a no-op), does it fire a duplicate backend call, does
it produce a duplicate run-history row for what should be one logical run,
does it break navigation into the Statistics view, or — the one to watch
for most closely given finding (4) — does it produce that same "silently
ends after a few seconds" symptom? If that symptom shows up here too, the
report below calls out explicitly whether it looks like the SAME underlying
bug as (4) (a race in the same start/stop state machine) or something
distinct (specific to double-submission of the click itself).

=== UI CHANGE (2026-09-17) — this test's whole click sequence was rebuilt ===
The two-step "Apply (Save & activate) -> wait for the post-Apply
'Deactivate' bar -> Start (run traffic)" flow this test was originally
written against no longer exists for a freshly-created draft testbed. The
"Apply" button is gone entirely; the draft's bottom bar is now Discard
Changes / Delete / Save / Start, and clicking Start pops a "Testbed is
Inactive" confirmation modal (Cancel / Continue) that activates AND starts
traffic together on Continue, landing straight in the Statistics view. See
test_t10_t12_lifecycle_multistream_udp_tcp_100mbps.py for the fullest
writeup of the product change itself.

That merger removes the old test's two distinct "kinds" of click target
(Apply = one-time, novel-state-creating; Start = repeatable, traffic-only)
that Phase 1 and Phase 2 below were built around. This version maps them
onto the closest equivalents in the new flow:

  - Phase 1 (was: double-click the repeatable "Start traffic" button on an
    already-armed testbed) now double-clicks **Continue** on the
    confirmation modal — Continue is the control that now actually fires
    the backend activate+start call for a first-ever activation, so it's
    the direct analog of the old test's "click the button that starts
    traffic" step. The single Start click that pops the modal is treated
    as the (single-click, well-trodden) arming step, matching the old
    test's single-click Apply before its double-click Start.
  - Phase 2 (was: double-click Apply itself, the one-time draft-arming
    action, on a second fresh testbed) now double-clicks **Start** itself
    on a second fresh draft, before any Continue click — Start's first-ever
    click is now the one-time, novel-state-creating action (it's what
    conjures the confirmation modal into existence), making it the closest
    analog of old Apply.

NEEDS HUMAN REVIEW: this mapping is a best-effort adaptation, not something
re-confirmed against live hardware yet (the original 2026-09-15 findings
below were captured under the OLD Apply/Start flow and are kept as
historical record of a real bug found that day — they do not describe
current button names or the current click sequence). Two assumptions in
particular need verification on the next live run:
  1. That a never-yet-activated draft testbed reliably shows the "Testbed
     is Inactive" modal on its first Start click (if a prior manual session
     left "Don't show this again" checked for this account, Phase 1 would
     have no modal/Continue to double-click at all — handled below by
     skipping loudly rather than silently reinterpreting the click target).
  2. What double-clicking Start itself actually does in Phase 2 — whether
     the second click event lands on the modal's own Continue by
     coordinate coincidence (in which case it behaves like a fast
     Start+Continue and ends up live), lands on the modal backdrop/no-op
     (single clean modal, no different from a single click), or produces
     some third, broken state. All three are handled and reported below,
     but which one this product actually does is exactly the open question
     this test exists to answer.

--- What was actually observed under the OLD Apply/Start flow (2026-09-15,
one run against 192.168.173.111) — kept as historical record; the button
names below (Apply, Deactivate) no longer exist in the current UI ---
Phase 1 ran; Phase 2 was never reached because Phase 1 surfaced a genuine
anomaly and the test correctly stopped there (per the "don't force a
pass" rule) rather than proceeding.

Build + Apply succeeded normally. The double-click itself looked clean by
every signal captured at click time: exactly ONE backend request matched
`/start` or `/activate` during the click window
(`POST /ctrl/v1/tests/T10-DblClick/start?wait=15`) — the frontend de-duped
the second click event rather than firing it twice. No console errors, no
uncaught page errors. Navigation into the Statistics view landed cleanly
(the "← Dashboard" button appeared within the wait). The run then went
genuinely live and ran for its FULL configured duration — Stop stayed
visible for 80.7s against an 80s configured ramp — so this is explicitly
NOT a recurrence of finding (4)'s "ends after ~2-4s" symptom; if anything
it's the opposite (full, correct-duration completion).

The anomaly showed up one step later. After Stop disappeared (natural
completion) and the dashboard tile's own "Stats" button was clicked —
verbatim the same action every sibling lifecycle test in this file uses
immediately after a completed run — the Statistics view did NOT show the
completed run's result or a populated `table.runs-table`. It showed the
same "Ready to start traffic / Ports are armed and idle. Start traffic to
begin collecting live statistics." empty/idle placeholder that only
otherwise appears right after Apply, before a testbed has ever been
started — as if the view had no memory that a run had just completed,
even though the backend evidence (single /start call, 80.7s of live Stop
visibility) confirms one genuinely did. `table.runs-table` never appeared
within a 10s wait. This is the same click-sequence and selector this
suite's other lifecycle tests use successfully
(test_t10_t12_lifecycle_udp_1gbps_1500b.py asserts "pass" text visible
immediately on this same click with no special handling;
test_t10_rapid_stop_restart_cycle.py asserts `table.runs-table` has the
expected row count the same way after its own natural-completion cycle) —
so this doesn't look like a selector or timing mistake in this test, it
looks like the double-click left this testbed's Stats/run-tracking view
state out of sync with the backend.

Verdict: **NOT the same bug as finding (4).** Finding (4) is a run
ending prematurely; here the run completed correctly and fully. This is
a distinct, third symptom from the task's anticipated list — "a confusing
UI state" — specific to double-submitting Start: the completed run seems
to have gone missing from its own Stats view, replaced by a stale
"never started" placeholder. One plausible mechanism (not confirmed):
the double-click's second `click` event landed on the *Statistics view's
own* "Start traffic" button (visible in the same view, at/near the
original Start button's screen position) microseconds after the SPA
navigated into it — which could plant a stale "about to start a fresh
run" expectation in the frontend's local state that then survives past
the real run's actual completion. This is a hypothesis to hand to
Travis/frontend, not a confirmed root cause — only one data point exists
(this suite's one-shot policy on stateful runs), so a genuine one-off
environmental flake on shared lab hardware can't be fully ruled out
either; it's flagged here because the balance of evidence (clean single
backend call, full-duration completion, an established selector/pattern
that works reliably elsewhere in this same file) points at a real
product/frontend bug rather than a mistake in this test.

Phase 2 (double-click Apply) was never attempted — per the task's explicit
instruction to stop and report rather than press on once Phase 1 produced
something worth flagging, and to avoid leaving a second testbed's state
tangled with an already-anomalous first one.

Hardware confirmed clean afterward (verified via a separate read-only
check after the test's own teardown fixture ran): Port 3 and Port 4 both
back to "Available", and neither T10-DblClick nor T10-DblApply remain
among the dashboard's testbed tiles (only the two pre-existing, unrelated
testbeds TA and TE-01 are present).

This whole test needs a fresh live run under the new UI before its
"Verdict" section above can be trusted as still-current — it is retained
only as historical evidence that double-submission bugs are a real,
previously-demonstrated risk area in this product, which is why this test
still exists and is worth re-running rather than deleting.

Stateful: generates real traffic on shared hardware. Only Port 3 and Port
4 are touched (Port 1/2 belong to other real users right now; Port 5/6 has
a known link-down hardware issue; Port 7/8 are unconfirmed) — same
constraint as every other test in this exploratory batch. Never run
alongside other stateful tests (no xdist, no parallel stateful runs, per
CLAUDE.md).

Selector/pattern notes carried over from the closest siblings
(test_t10_t12_lifecycle_udp_1gbps_1500b.py, test_t10_rapid_stop_restart_cycle.py):
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`); the post-Start/Continue
navigation into the Statistics view takes real time to complete (`?wait=15`
server-side contract), so waits for it are given generous room (75s)
rather than treated as hung; a hard `page.goto()`/back-nav mid-transition
is known to crash this SPA's routing, so the app's own "← Dashboard"
button is used to navigate back wherever possible.
"""
from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed names must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see netropy-ui-findings.md,
# "Testbed activation 502s permanently").
TESTBED_NAME = "T10-DblClick"
# Used for Phase 2's fresh-draft double-click-on-Start probe (renamed in
# spirit from its old "double-click Apply" role — see module docstring's
# UI CHANGE section for the mapping rationale; kept the same constant name
# to avoid an unrelated diff).
APPLY_TESTBED_NAME = "T10-DblApply"
assert_activatable_name(TESTBED_NAME)
assert_activatable_name(APPLY_TESTBED_NAME)

# Only Port 3 + Port 4 are confirmed safe right now (2026-09-15 constraint
# from Logan) — Port 1/2 belong to other real users, Port 5/6 has a known
# link-down issue, Port 7/8 are unconfirmed.
PORTS = ["Port 3", "Port 4"]
BUFFER_MS = 400

# 10/60/10 = 80s total ramp. Generous and, critically, long enough that if
# the run ends dramatically early (finding (4)'s "~2-4s instead of
# configured duration" symptom) it's unambiguous against this floor rather
# than lost in normal timing noise.
RAMP = (10, 60, 10)
RAMP_TOTAL_S = sum(RAMP)
# How long Stop must stay visible before we're willing to call an early
# end "premature" rather than just brisk UI/activation lag. Comfortably
# below RAMP_TOTAL_S, comfortably above the ~2-4s finding (4) symptom.
PREMATURE_END_THRESHOLD_S = 25


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


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


def _release_ports(page: Page):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        # A failure mid-wizard (before Save/Start) leaves unsaved edits, so
        # navigating away pops an "Unsaved changes" confirm modal.
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)
    for port_label in PORTS:
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
    _delete_testbed_if_present(dashboard, TESTBED_NAME)
    _delete_testbed_if_present(dashboard, APPLY_TESTBED_NAME)
    yield
    _release_ports(dashboard)
    _delete_testbed_if_present(dashboard, TESTBED_NAME)
    _delete_testbed_if_present(dashboard, APPLY_TESTBED_NAME)


def _reserve_ports(page: Page):
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)


def _build_udp_testbed(page: Page, name: str, ip_base: str):
    """Build a single-UDP-stream Traffic Engine testbed on Port 3 + Port 4,
    1 Gbps line rate, 1500-byte frames, RAMP ramp. Stops at the end of wizard
    configuration WITHOUT clicking Start — both phases of this test need to
    control that click themselves (single vs. double) as part of the probe
    under test, so it isn't baked into this helper the way an ordinary
    lifecycle test's Apply click used to be. Mirrors
    test_t10_t12_lifecycle_udp_1gbps_1500b.py step for step otherwise.
    """
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(name)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # Always target the tile by name, never by position (see project bugs
    # memory — a positional Edit index silently corrupted an unrelated
    # testbed once a 4th tile existed on the dashboard).
    _testbed_tile(page, name).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(3) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(4) > td > div > .toggle > .track").click()
    _buffer(page)
    for port_label in PORTS:
        rate_field = page.get_by_role(
            "row", name=re.compile(rf"^{re.escape(port_label)}\b")
        ).get_by_placeholder("line rate")
        rate_field.fill("1")
        _buffer(page)
    page.get_by_role(
        "row", name=re.compile(r"^Port 4\b")
    ).get_by_placeholder("line rate").press("Enter")
    _buffer(page)

    page.get_by_role("button", name="2 Network Configuration per-").click()
    _buffer(page)
    ip1, ip2 = f"{ip_base}1", f"{ip_base}2"
    page.get_by_role("textbox", name="10.1.0.10").first.fill(ip1)
    _buffer(page)
    page.locator(".seg").first.select_option("25")
    _buffer(page)
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill(ip2)
    _buffer(page)
    page.locator(
        "div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main "
        "> div > div:nth-child(2) > .ne-combo > select"
    ).select_option("25")
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
    frame_size = page.locator("td:nth-child(5) > .fc").first
    frame_size.fill("1500")
    _buffer(page)
    frame_size.press("Enter")
    _buffer(page)

    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    up, hold, down = RAMP
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


def _run_history_rows(page: Page):
    return page.locator("table.runs-table tbody tr")


@pytest.mark.stateful
def test_t10_double_click_start_race(dashboard: Page, clean_testbeds):
    page = dashboard

    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None,
    )
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # =========================================================================
    # Phase 1: build one UDP testbed, single-click Start to reach the
    # "Testbed is Inactive" confirmation modal, then double-click Continue —
    # the control that now actually fires the backend activate+start call
    # (see module docstring's UI CHANGE section for why Continue, not Start,
    # is this phase's target under the new merged flow).
    # =========================================================================
    _reserve_ports(page)
    _build_udp_testbed(page, TESTBED_NAME, ip_base="10.0.9.")

    start_btn = page.get_by_role("button", name="Start", exact=True)
    expect(start_btn).to_be_visible()
    start_btn.click()
    _buffer(page)

    continue_btn = page.get_by_role("button", name="Continue", exact=True)
    # NEEDS HUMAN REVIEW: see module docstring assumption (1). If this ever
    # fires, the account-level "Don't show this again" preference has
    # apparently been left set from a prior manual session, and this
    # phase's whole premise (double-click the button that fires the actual
    # backend call) needs to be re-pointed at Start itself instead.
    if not continue_btn.is_visible():
        pytest.skip(
            "The 'Testbed is Inactive' confirmation modal did not appear "
            "after a single Start click on a never-yet-activated draft — "
            "this test's assumption that Continue is the control that "
            "fires the actual activate+start call does not hold here "
            "(likely 'Don't show this again' is set for this account). "
            "NEEDS HUMAN REVIEW before adapting this test further."
        )

    # Drop any console/page-error noise accumulated during wizard navigation
    # — only the double-click window itself is the thing under test.
    console_errors.clear()
    page_errors.clear()

    start_requests: list[tuple[str, str]] = []

    def _capture_start_request(req):
        if "/start" in req.url or "/activate" in req.url:
            start_requests.append((req.method, req.url))

    page.on("request", _capture_start_request)

    url_before = page.url

    t0 = time.monotonic()
    # The literal double-click gesture: Playwright dispatches two real
    # `click` events (plus a browser-level `dblclick`) as one gesture,
    # without re-running actionability checks between them — the closest
    # thing to an actual impatient double-click race, closer than two
    # independently-actionability-checked .click() calls would be.
    continue_btn.click(click_count=2)
    click_gesture_s = time.monotonic() - t0

    # Give the SPA a moment to settle wherever the double-click left it
    # before reading state.
    page.wait_for_timeout(2000)
    page.remove_listener("request", _capture_start_request)

    print(f"\n[dblclick probe] Continue click(click_count=2) gesture took {click_gesture_s:.3f}s")
    print(f"[dblclick probe] url before={url_before!r} url immediately after settle={page.url!r}")
    print(f"[dblclick probe] backend requests matching /start or /activate during the click window: {start_requests}")
    print(f"[dblclick probe] console errors during click window: {console_errors}")
    print(f"[dblclick probe] uncaught page errors during click window: {page_errors}")

    assert not page_errors, (
        "BUG: double-clicking Continue threw an uncaught page-level JS "
        f"error — the double-submit crashed something client-side: {page_errors}"
    )

    # --- Did it land in the Statistics view cleanly, or somewhere broken? ---
    stats_heading = page.get_by_role("heading", name="Statistics", exact=False)
    landed_in_stats = False
    try:
        expect(stats_heading).to_be_visible(timeout=15000)
        landed_in_stats = True
    except Exception:
        body_preview = page.locator("body").inner_text()[:600]
        print(f"[dblclick probe] NOT in Statistics view after double-clicking Continue. Body preview: {body_preview!r}")

    assert landed_in_stats, (
        "BUG: double-clicking Continue did not land cleanly in the "
        "Statistics view within 15s — the second click event appears to "
        "have broken navigation (stuck on the modal, blank, or otherwise "
        "off the expected post-Continue route)."
    )

    # Get back to the dashboard the SPA-safe way (hard goto/back-nav is
    # known to crash mid-transition — see reference test docstring).
    stats_dashboard_btn = page.get_by_role("button", name="← Dashboard")
    stats_dashboard_btn.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)

    tile = _testbed_tile(page, TESTBED_NAME)

    # --- Confirm the run actually went live (Stop visible), then time how
    # long it stays live — this is where finding (4)'s "silently ends
    # after ~2-4s" symptom would show up, if the double-click triggered
    # the same (or a related) state-machine race. ---
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    live_since = time.monotonic()

    stop_visible_for_s = None
    # Poll rather than a single long expect() so we can report exactly how
    # long the run stayed live, not just pass/fail against a timeout.
    deadline = live_since + RAMP_TOTAL_S + 90  # ramp + generous activation/UI slack
    while time.monotonic() < deadline:
        if tile.get_by_role("button", name="Stop").count() == 0:
            stop_visible_for_s = time.monotonic() - live_since
            break
        page.wait_for_timeout(1000)
    else:
        stop_visible_for_s = time.monotonic() - live_since

    print(f"[dblclick probe] Stop button was visible for {stop_visible_for_s:.1f}s "
          f"(configured ramp totals {RAMP_TOTAL_S}s)")

    assert stop_visible_for_s >= PREMATURE_END_THRESHOLD_S, (
        f"BUG: after double-clicking Continue, the run ended after only "
        f"{stop_visible_for_s:.1f}s — well short of the {RAMP_TOTAL_S}s "
        f"configured ramp and under the {PREMATURE_END_THRESHOLD_S}s "
        "premature-end threshold. This matches the shape of the known "
        "finding: restarting Start on a just-Stopped testbed can cause a "
        "run to silently self-terminate after ~2-4s "
        "(test_t10_rapid_stop_restart_cycle.py's discovery) — this may be "
        "the SAME underlying start/stop state-machine race, now reachable "
        "via a double-click on Continue rather than a restart. No error "
        "was shown anywhere in the UI for this early end."
    )

    # --- Run-history integrity: exactly one row for what should be one
    # logical run, not a duplicate/corrupted entry from the double-submit. ---
    tile.get_by_role("button", name="Stats").click()
    rows = _run_history_rows(page)
    expect(rows.first).to_be_visible(timeout=10000)
    row_count = rows.count()
    print(f"[dblclick probe] run-history row count after one double-clicked Continue: {row_count}")

    assert row_count == 1, (
        f"BUG: double-clicking Continue produced {row_count} run-history "
        "rows for what should be exactly one logical run — the second "
        "click event appears to have triggered a duplicate "
        f"activation/start attempt recorded as its own run. Backend "
        f"requests captured during the click window: {start_requests}"
    )

    result_text = rows.first.locator("td").last.inner_text().strip()
    print(f"[dblclick probe] single run-history row result: {result_text!r}")

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    print(
        "[dblclick probe] Phase 1 (double-click Continue) verdict: no "
        "duplicate backend call side effects, no duplicate run-history "
        "row, no premature end, no broken navigation, no uncaught JS "
        "error — double-click on Continue appears to be handled as "
        "idempotent/robust by this product."
    )

    # =========================================================================
    # Phase 2 (only reached if Phase 1 found nothing worth stopping for):
    # fully clean up Phase 1's testbed, then double-click Start itself — its
    # first-ever click, before any Continue — on a fresh, unactivated draft.
    # This is the analog of the old test's "double-click Apply" (the
    # one-time, novel-state-creating action): Start's first click is what
    # now conjures the confirmation modal into existence for a never-yet-
    # activated testbed.
    # =========================================================================
    _release_ports(page)
    _delete_testbed_if_present(page, TESTBED_NAME)

    _reserve_ports(page)
    _build_udp_testbed(page, APPLY_TESTBED_NAME, ip_base="10.0.10.")

    apply_requests: list[tuple[str, str]] = []

    def _capture_apply_request(req):
        if req.method in ("POST", "PUT") and (
            "/tests" in req.url or "/activate" in req.url or "/start" in req.url
        ):
            apply_requests.append((req.method, req.url))

    page.on("request", _capture_apply_request)
    console_errors.clear()
    page_errors.clear()

    start_btn_2 = page.get_by_role("button", name="Start", exact=True)
    expect(start_btn_2).to_be_visible()
    start_btn_2.click(click_count=2)

    page.wait_for_timeout(2000)
    page.remove_listener("request", _capture_apply_request)

    print(f"[dblclick probe] backend requests matching save/activate/start during the "
          f"fresh-draft Start double-click window: {apply_requests}")
    print(f"[dblclick probe] console errors during Start double-click: {console_errors}")
    print(f"[dblclick probe] page errors during Start double-click: {page_errors}")

    assert not page_errors, (
        "BUG: double-clicking a fresh draft's Start button threw an "
        f"uncaught page-level JS error: {page_errors}"
    )

    # NEEDS HUMAN REVIEW (see module docstring assumption (2)): a
    # double-click on Start's very first click could plausibly resolve to
    # any of three outcomes — (a) a single, clean confirmation modal still
    # waiting for a real Continue click (second click event was a no-op,
    # e.g. it hit the backdrop), (b) already live in the Statistics view
    # (second click event happened to land on the modal's own Continue by
    # coordinate coincidence, behaving like a fast single-click-through),
    # or (c) neither — a broken, stuck state. All three are checked for
    # explicitly below rather than assumed.
    continue_btn_2 = page.get_by_role("button", name="Continue", exact=True)
    stats_heading_2 = page.get_by_role("heading", name="Statistics", exact=False)
    modal_open = continue_btn_2.is_visible()
    in_statistics = stats_heading_2.is_visible()
    print(f"[dblclick probe] After double-clicking a fresh draft's Start: "
          f"modal_open={modal_open}, in_statistics={in_statistics}")

    assert not (modal_open and in_statistics), (
        "BUG: double-clicking Start left the UI showing BOTH the "
        "confirmation modal AND the Statistics view's heading at once — a "
        "confusing/inconsistent dual state."
    )
    assert modal_open or in_statistics, (
        "BUG: double-clicking Start on a fresh, never-activated draft left "
        "the UI in neither the confirmation modal NOR the Statistics view "
        "— the second click event appears to have broken the "
        "draft-to-active transition entirely (stuck mid-wizard, blank, or "
        "otherwise unrecoverable without a manual reload)."
    )

    if modal_open:
        continue_count = page.get_by_role("button", name="Continue", exact=True).count()
        assert continue_count == 1, (
            f"BUG: double-clicking Start left {continue_count} 'Continue' "
            "controls on screen instead of one — looks like a duplicated "
            "confirmation modal."
        )
        print(
            "[dblclick probe] Phase 2 verdict: double-clicking a fresh "
            "draft's Start button left a single, clean confirmation modal "
            "— the second click event did not advance past it or "
            "duplicate it. Dismissing without activating (Cancel), since "
            "this probe's job is the click race itself, not a second live "
            "traffic cycle."
        )
        cancel_btn = page.get_by_role("button", name="Cancel", exact=True)
        if cancel_btn.is_visible():
            cancel_btn.click()
            _buffer(page)
    else:
        print(
            "[dblclick probe] Phase 2 verdict: double-clicking a fresh "
            "draft's Start button landed directly in the Statistics view "
            "— NEEDS HUMAN REVIEW: confirm on a live run whether this "
            "means the second click landed on the modal's own Continue "
            "button by coordinate coincidence (benign — equivalent to a "
            "fast manual Start+Continue), or whether the product now "
            "silently skips confirmation on a double-click of Start (a "
            "real product quirk worth flagging, since a single accidental "
            "double-click would then activate+start traffic with no "
            "chance to back out via Cancel)."
        )

    # Get back to the dashboard however the branch above left the page.
    dash_btn_2 = page.get_by_role("button", name="← Dashboard")
    if dash_btn_2.is_visible():
        dash_btn_2.click()
        _buffer(page)
        discard_btn_2 = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn_2.is_visible():
            discard_btn_2.click()
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)

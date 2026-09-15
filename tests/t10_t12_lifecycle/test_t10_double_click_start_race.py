"""T10 — double-click race on Start (and, budget permitting, on Apply).

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
mouse (or an impatient double-tap) sends the wizard's Start button *two*
click events back to back, right after Apply has just armed the testbed?
Single-click Start here is well-trodden ground (every other lifecycle test
in this file uses it) — the untried part is the *double*-click, which
touches the same state-transition territory as finding (4) above: does the
frontend de-dupe it (second click is a no-op), does it fire a duplicate
backend call, does it produce a duplicate run-history row for what should
be one logical run, does it break navigation into the Statistics view, or —
the one to watch for most closely given finding (4) — does it produce that
same "silently ends after a few seconds" symptom? If that symptom shows up
here too, the report below calls out explicitly whether it looks like the
SAME underlying bug as (4) (a race in the same start/stop state machine) or
something distinct (specific to double-submission of the click itself).

Phase 1 (always run): build one UDP testbed on Port 3 + Port 4 (10/60/10s
ramp — generous, so a premature end is unambiguous against the 80s
expected floor), Apply it, wait for the post-Apply "Deactivate" bar
(armed, not started), then fire `Start.click(click_count=2)` — Playwright's
literal double-click gesture, which dispatches two real `click` events at
the DOM level in rapid succession, closer to an actual double-click race
than two independently-actionability-checked `.click()` calls would be.
Backend requests matching `/start` or `/activate` are captured via a
`page.on("request")` listener across the click window as a direct,
UI-independent signal of whether one or two calls actually went out.
Console errors and uncaught page errors are captured the same way.

Phase 2 (only reached if Phase 1 found nothing — see the "stop, don't
force a pass" rule below): after fully cleaning up Phase 1's testbed and
releasing Port 3/4 back to Available, build a second, unapplied UDP
testbed and double-click *Apply* itself the same way, watching for a
duplicate save/activate call or a broken post-Apply bar. This is the
"budget permitting" second angle from the task — cheap to attempt since it
reuses the same ports and pattern, and worth checking since Apply is the
one-time, novel-state-creating twin of the many-times-repeatable Start.

Stateful: generates real traffic on shared hardware. Only Port 3 and Port
4 are touched (Port 1/2 belong to other real users right now; Port 5/6 has
a known link-down hardware issue; Port 7/8 are unconfirmed) — same
constraint as every other test in this exploratory batch. Never run
alongside other stateful tests (no xdist, no parallel stateful runs, per
CLAUDE.md).

Selector/pattern notes carried over from the closest siblings
(test_t10_t12_lifecycle_udp_1gbps_1500b.py, test_t10_rapid_stop_restart_cycle.py):
several wizard controls have no accessible name/role/data-testid and fall
back to CSS position (`.fc`, `.seg`, `nth-child`); the post-Apply action
bar takes real time to swap in (`?wait=15` server-side contract), so the
wait for "Deactivate" is given generous room (75s) rather than treated as
hung; a hard `page.goto()`/back-nav mid-transition is known to crash this
SPA's routing, so the app's own "← Dashboard" button is used to navigate
back wherever possible.

--- What was actually observed (2026-09-15, one run against
192.168.173.111) ---
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
        # A failure mid-wizard (before Apply/Save) leaves unsaved edits, so
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


def _build_udp_testbed(page: Page, name: str, ip_base: str, *, apply: bool):
    """Build a single-UDP-stream Traffic Engine testbed on Port 3 + Port 4,
    1 Gbps line rate, 1500-byte frames, RAMP ramp. Optionally clicks Apply
    at the end (Phase 2 needs to stop just short, so it can double-click
    Apply itself). Mirrors test_t10_t12_lifecycle_udp_1gbps_1500b.py step
    for step.
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

    if apply:
        page.get_by_role("button", name="Apply", exact=True).click()
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
    # Phase 1: build + Apply one UDP testbed, then double-click Start on the
    # freshly-armed ("Deactivate" bar showing) testbed.
    # =========================================================================
    _reserve_ports(page)
    _build_udp_testbed(page, TESTBED_NAME, ip_base="10.0.9.", apply=True)

    # Post-Apply bar (Delete/Deactivate/Stats/Save/Start) — testbed is armed,
    # not yet started. Real room given for the ?wait=15 activate contract
    # plus UI lag, same as every other activating test in this suite.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)

    # Drop any console/page-error noise accumulated during wizard navigation
    # — only the double-click window itself is the thing under test.
    console_errors.clear()
    page_errors.clear()

    start_requests: list[tuple[str, str]] = []

    def _capture_start_request(req):
        if "/start" in req.url or "/activate" in req.url:
            start_requests.append((req.method, req.url))

    page.on("request", _capture_start_request)

    start_btn = page.get_by_role("button", name="Start")
    expect(start_btn).to_be_visible()
    url_before = page.url

    t0 = time.monotonic()
    # The literal double-click gesture: Playwright dispatches two real
    # `click` events (plus a browser-level `dblclick`) as one gesture,
    # without re-running actionability checks between them — the closest
    # thing to an actual impatient double-click race, closer than two
    # independently-actionability-checked .click() calls would be.
    start_btn.click(click_count=2)
    click_gesture_s = time.monotonic() - t0

    # Give the SPA a moment to settle wherever the double-click left it
    # before reading state.
    page.wait_for_timeout(2000)
    page.remove_listener("request", _capture_start_request)

    print(f"\n[dblclick probe] Start click(click_count=2) gesture took {click_gesture_s:.3f}s")
    print(f"[dblclick probe] url before={url_before!r} url immediately after settle={page.url!r}")
    print(f"[dblclick probe] backend requests matching /start or /activate during the click window: {start_requests}")
    print(f"[dblclick probe] console errors during click window: {console_errors}")
    print(f"[dblclick probe] uncaught page errors during click window: {page_errors}")

    assert not page_errors, (
        "BUG: double-clicking Start threw an uncaught page-level JS error — "
        f"the double-submit crashed something client-side: {page_errors}"
    )

    # --- Did it land in the Statistics view cleanly, or somewhere broken? ---
    # Single-click Start from this wizard-level bar navigates into the
    # Statistics view (unlike the dashboard-tile Start used by
    # test_t10_rapid_stop_restart_cycle.py, which stays on the dashboard).
    stats_dashboard_btn = page.get_by_role("button", name="← Dashboard")
    landed_in_stats = False
    try:
        expect(stats_dashboard_btn).to_be_visible(timeout=15000)
        landed_in_stats = True
    except Exception:
        body_preview = page.locator("body").inner_text()[:600]
        print(f"[dblclick probe] NOT in Statistics view after double-click. Body preview: {body_preview!r}")

    assert landed_in_stats, (
        "BUG: double-clicking Start did not land cleanly in the Statistics "
        "view within 15s — the second click event appears to have broken "
        "navigation (stuck mid-wizard, blank, or otherwise off the "
        "expected post-Start route)."
    )

    # Get back to the dashboard the SPA-safe way (hard goto/back-nav is
    # known to crash mid-transition — see reference test docstring).
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
        f"BUG: after double-clicking Start, the run ended after only "
        f"{stop_visible_for_s:.1f}s — well short of the {RAMP_TOTAL_S}s "
        f"configured ramp and under the {PREMATURE_END_THRESHOLD_S}s "
        "premature-end threshold. This matches the shape of the known "
        "finding: restarting Start on a just-Stopped testbed can cause a "
        "run to silently self-terminate after ~2-4s "
        "(test_t10_rapid_stop_restart_cycle.py's discovery) — this may be "
        "the SAME underlying start/stop state-machine race, now reachable "
        "via a double-click on the very first Start rather than a restart. "
        "No error was shown anywhere in the UI for this early end."
    )

    # --- Run-history integrity: exactly one row for what should be one
    # logical run, not a duplicate/corrupted entry from the double-submit. ---
    tile.get_by_role("button", name="Stats").click()
    rows = _run_history_rows(page)
    expect(rows.first).to_be_visible(timeout=10000)
    row_count = rows.count()
    print(f"[dblclick probe] run-history row count after one double-clicked Start: {row_count}")

    assert row_count == 1, (
        f"BUG: double-clicking Start produced {row_count} run-history rows "
        "for what should be exactly one logical run — the second click "
        "event appears to have triggered a duplicate activation/start "
        f"attempt recorded as its own run. Backend requests captured "
        f"during the click window: {start_requests}"
    )

    result_text = rows.first.locator("td").last.inner_text().strip()
    print(f"[dblclick probe] single run-history row result: {result_text!r}")

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    print(
        "[dblclick probe] Phase 1 (double-click Start) verdict: no duplicate "
        "backend call side effects, no duplicate run-history row, no "
        "premature end, no broken navigation, no uncaught JS error — "
        "double-click on Start appears to be handled as idempotent/robust "
        "by this product."
    )

    # =========================================================================
    # Phase 2 (only reached if Phase 1 found nothing worth stopping for):
    # fully clean up Phase 1's testbed, then double-click Apply itself on a
    # fresh unapplied testbed, watching for a duplicate save/activate call.
    # =========================================================================
    _release_ports(page)
    _delete_testbed_if_present(page, TESTBED_NAME)

    _reserve_ports(page)
    _build_udp_testbed(page, APPLY_TESTBED_NAME, ip_base="10.0.10.", apply=False)

    apply_requests: list[tuple[str, str]] = []

    def _capture_apply_request(req):
        if req.method in ("POST", "PUT") and (
            "/tests" in req.url or "/activate" in req.url
        ):
            apply_requests.append((req.method, req.url))

    page.on("request", _capture_apply_request)
    console_errors.clear()
    page_errors.clear()

    apply_btn = page.get_by_role("button", name="Apply", exact=True)
    expect(apply_btn).to_be_visible()
    apply_btn.click(click_count=2)

    # Same ?wait=15-plus-UI-lag contract as a normal single Apply.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.wait_for_timeout(2000)
    page.remove_listener("request", _capture_apply_request)

    print(f"[dblclick probe] backend requests matching save/activate during the Apply "
          f"double-click window: {apply_requests}")
    print(f"[dblclick probe] console errors during Apply double-click: {console_errors}")
    print(f"[dblclick probe] page errors during Apply double-click: {page_errors}")

    assert not page_errors, (
        "BUG: double-clicking Apply threw an uncaught page-level JS error: "
        f"{page_errors}"
    )

    # A single, clean post-Apply bar (Deactivate visible exactly once —
    # to_be_visible() above already confirms presence; here confirm there
    # isn't a duplicated/broken second bar rendered alongside it).
    deactivate_buttons = page.get_by_role("button", name="Deactivate")
    assert deactivate_buttons.count() == 1, (
        f"BUG: double-clicking Apply left {deactivate_buttons.count()} "
        "'Deactivate' controls on screen instead of one — looks like a "
        "duplicated/corrupted post-Apply action bar."
    )

    print(
        f"[dblclick probe] Phase 2 (double-click Apply) verdict: reached a single "
        "clean post-Apply state, no uncaught JS error. Backend call count for "
        f"manual review: {len(apply_requests)} request(s) captured "
        f"({apply_requests})."
    )

    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

"""T3 — Reserving a port already held "by another session".

The plan asks to test "reserve a port already held by another session
→ blocked with clear error (needs second storageState)". This box only
has one configured test account (`test`/`test` — see .env.example,
confirmed via T1's concurrent-sessions test using the same credentials
for both contexts), so there's no second real user identity available
to reproduce a genuine cross-user reservation conflict.

What's actually confirmed here instead: reservation is scoped to the
*account*, not the browser session/tab. A second browser context signed
into the same account sees the port as already "Reserved By: test
(you)" too — "(you)" tracks the account, not the tab — and gets a
Release button instead of Reserve, with no conflict/error state at all.
There's nothing to block because the second tab already owns it. This
is a genuine environmental limitation, not a shortcut: worth relaying
to Travis if a second test account ever becomes available, so the
literal cross-user scenario can be covered.

On pages/ (2026-10-11): the second tab is a second context from the same saved session.
"""
import json

import pytest
from playwright.sync_api import Page, expect

from conftest import SESSION_STORAGE_FILE, STATE_FILE
from pages import DashboardPage, settings


@pytest.fixture
def free_port(dashboard: Page):
    """A port nobody holds; released again afterwards if this test left it
    reserved (it only ever releases the port it picked)."""
    board = DashboardPage(dashboard)
    port = board.first_unreserved_port()
    if port is None:
        pytest.skip("No unreserved port: all 8 may be held by other users")
    yield port
    if board.port_row(port).get_by_role("button", name="Release", exact=True).is_visible():
        board.release_port(port)


@pytest.mark.stateful
def test_t3_second_tab_same_account_sees_own_reservation_not_a_conflict(dashboard: Page, free_port):
    board_a = DashboardPage(dashboard)
    board_a.reserve_port(free_port)

    session_storage = json.loads(SESSION_STORAGE_FILE.read_text())
    init_script = "".join(
        f"window.sessionStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
        for k, v in session_storage.items()
    )
    context_b = dashboard.context.browser.new_context(
        base_url=settings.NTG_URL, storage_state=str(STATE_FILE)
    )
    try:
        context_b.add_init_script(init_script)
        page_b = context_b.new_page()
        board_b = DashboardPage(page_b)
        board_b.open()
        row_b = board_b.port_row(free_port)
        expect(row_b.get_by_text("Reserved", exact=True)).to_be_visible()
        expect(row_b).to_contain_text(settings.NTG_USER)
        expect(row_b.get_by_role("button", name="Reserve", exact=True)).to_have_count(0)
        expect(row_b.get_by_role("button", name="Release", exact=True)).to_be_visible()
    finally:
        context_b.close()

    board_a.release_port(free_port)

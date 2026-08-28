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
"""
import json
import os
import pathlib

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

load_dotenv()
BASE_URL = os.environ["NETROPY_URL"].rstrip("/")
STATE_FILE = pathlib.Path(__file__).parent.parent.parent / ".auth_state.json"
SESSION_STORAGE_FILE = (
    pathlib.Path(__file__).parent.parent.parent / ".auth_session_storage.json"
)


def _first_available_port(page: Page) -> str:
    for n in range(1, 9):
        row = page.get_by_role("row", name=f"Port {n}")
        if row.get_by_text("Available", exact=True).is_visible():
            return f"Port {n}"
    pytest.skip("No available port found — all 8 may be reserved by other users")


@pytest.mark.stateful
def test_t3_second_tab_same_account_sees_own_reservation_not_a_conflict(dashboard: Page):
    page_a = dashboard
    port_label = _first_available_port(page_a)
    row_a = page_a.get_by_role("row", name=port_label)

    row_a.get_by_role("button", name="Reserve").click()
    expect(row_a.get_by_text("Reserved", exact=True)).to_be_visible()

    # A second, independent context using the same saved auth state — the
    # `dashboard` fixture's own context/page fixture pattern, replicated
    # here since a second concurrent session can't reuse the first one's
    # single `page`.
    session_storage = json.loads(SESSION_STORAGE_FILE.read_text())
    init_script = "".join(
        f"window.sessionStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
        for k, v in session_storage.items()
    )
    context_b = page_a.context.browser.new_context(
        base_url=BASE_URL, storage_state=str(STATE_FILE)
    )
    try:
        context_b.add_init_script(init_script)
        page_b = context_b.new_page()
        page_b.goto("/")
        expect(page_b.get_by_text("Port Status")).to_be_visible()

        row_b = page_b.get_by_role("row", name=port_label)
        expect(row_b.get_by_text("Reserved", exact=True)).to_be_visible()
        expect(row_b).to_contain_text("test")
        expect(row_b.get_by_role("button", name="Reserve")).to_have_count(0)
        expect(row_b.get_by_role("button", name="Release")).to_be_visible()
    finally:
        context_b.close()

    row_a.get_by_role("button", name="Release").click()
    expect(row_a.get_by_text("Available", exact=True)).to_be_visible()

"""T1 authentication — two concurrent sessions for the same user both work.

Standalone split of one test from test_t1_auth_all.py so it can run in
isolation; see that file for the full combined T1 suite.

This test exercises login directly, so it uses fresh browser contexts
instead of the session-authenticated `page`/`dashboard` fixtures — the
whole point here is testing the login flow itself.
"""
import os

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Browser, expect

load_dotenv()

BASE_URL = os.environ["NETROPY_URL"].rstrip("/")
USERNAME = os.environ["NETROPY_USER"]
PASSWORD = os.environ["NETROPY_PASS"]


def _sign_in(page, username: str, password: str) -> None:
    page.goto("/")
    page.get_by_placeholder("username").fill(username)
    page.get_by_placeholder("password").fill(password)
    page.get_by_role("button", name="Sign in").click()


@pytest.mark.hardware_free
def test_t1_two_concurrent_sessions_both_work(browser: Browser):
    context_a = browser.new_context(base_url=BASE_URL)
    context_b = browser.new_context(base_url=BASE_URL)
    try:
        for context in (context_a, context_b):
            page = context.new_page()
            _sign_in(page, USERNAME, PASSWORD)
            expect(page.get_by_text("Port Status")).to_be_visible()
    finally:
        context_a.close()
        context_b.close()

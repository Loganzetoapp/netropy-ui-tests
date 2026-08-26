"""T1 authentication — logout returns to login and kills the session.

Standalone split of one test from test_t1_auth_all.py so it can run in
isolation; see that file for the full combined T1 suite.

This test exercises login/logout directly, so it uses a fresh browser
context instead of the session-authenticated `page`/`dashboard` fixtures —
the whole point here is testing the login flow itself.
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
def test_t1_logout_returns_to_login_and_kills_session(browser: Browser):
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    _sign_in(page, USERNAME, PASSWORD)
    expect(page.get_by_text("Port Status")).to_be_visible()

    page.get_by_role("button", name="Menu").click()
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()

    # This SPA doesn't push a history entry for login/logout, so go_back()
    # lands on about:blank rather than the login form — the property that
    # actually matters is that the dashboard doesn't reappear.
    page.go_back()
    expect(page.get_by_text("Port Status")).not_to_be_visible()
    context.close()

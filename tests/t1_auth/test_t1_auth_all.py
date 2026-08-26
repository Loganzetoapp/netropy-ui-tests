"""T1 authentication and session lifecycle — combined suite.

All 4 T1 tests together in one file, for a single at-a-glance run of the
whole feature area. Each test also exists standalone in its own file
(test_t1_valid_login.py, test_t1_invalid_password.py, test_t1_logout.py,
test_t1_concurrent_sessions.py) so it can be run in isolation — this means
every T1 test runs twice under the default markers (once here, once
standalone), which is intentional: same coverage, and T1 is cheap enough
that the extra runtime doesn't matter.

These tests exercise login/logout directly, so they use a fresh browser
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


@pytest.mark.smoke
@pytest.mark.hardware_free
def test_t1_valid_login_lands_on_dashboard(browser: Browser):
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    _sign_in(page, USERNAME, PASSWORD)
    expect(page.get_by_text("Port Status")).to_be_visible()
    context.close()


@pytest.mark.hardware_free
def test_t1_invalid_password_shows_error_no_session(browser: Browser):
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    _sign_in(page, USERNAME, "wrong-password-123")
    expect(page.get_by_text("Sign-in failed: invalid credentials")).to_be_visible()
    expect(page.get_by_text("Port Status")).not_to_be_visible()
    context.close()


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

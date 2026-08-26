"""T1 authentication — invalid password shows error, no session.

Standalone split of one test from test_t1_auth_all.py so it can run in
isolation; see that file for the full combined T1 suite.

This test exercises login directly, so it uses a fresh browser context
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
def test_t1_invalid_password_shows_error_no_session(browser: Browser):
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    _sign_in(page, USERNAME, "wrong-password-123")
    expect(page.get_by_text("Sign-in failed: invalid credentials")).to_be_visible()
    expect(page.get_by_text("Port Status")).not_to_be_visible()
    context.close()

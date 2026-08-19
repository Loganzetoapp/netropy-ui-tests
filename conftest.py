"""Shared fixtures for the Netropy UI test suite.

Auth strategy: log in once per session, save storage state to disk,
reuse it for every test. If the saved state goes stale the setup
fixture logs in again.
"""
import json
import os
import pathlib
import re

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

load_dotenv()

BASE_URL = os.environ["NETROPY_URL"].rstrip("/")
USERNAME = os.environ["NETROPY_USER"]
PASSWORD = os.environ["NETROPY_PASS"]

STATE_FILE = pathlib.Path(__file__).parent / ".auth_state.json"
# The app keeps its session token in sessionStorage ("tgen-session"), which
# Playwright's storage_state() does not capture (it only persists cookies
# and localStorage). We snapshot it separately and replay it into every new
# context via an init script, otherwise each fresh context boots with no
# token and the app bounces straight back to the sign-in screen.
SESSION_STORAGE_FILE = pathlib.Path(__file__).parent / ".auth_session_storage.json"

# Default timeout for expect() assertions (ms)
expect.set_options(timeout=10_000)


def _login(page: Page) -> None:
    """Log in through the UI."""
    page.goto(BASE_URL)
    # If we land on the dashboard already, session is valid
    try:
        page.wait_for_selector("text=Port Status", timeout=3000)
        return
    except Exception:
        pass
    page.get_by_placeholder("username").fill(USERNAME)
    page.get_by_placeholder("password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Port Status")).to_be_visible()


@pytest.fixture(scope="session")
def auth_state(browser) -> dict:
    """Log in once per session and persist storage state + session storage."""
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    _login(page)
    context.storage_state(path=str(STATE_FILE))
    session_storage = json.loads(page.evaluate("() => JSON.stringify(sessionStorage)"))
    SESSION_STORAGE_FILE.write_text(json.dumps(session_storage))
    context.close()
    return {"storage_state": str(STATE_FILE), "session_storage": session_storage}


@pytest.fixture
def page(browser, auth_state) -> Page:
    """An authenticated page. Overrides pytest-playwright's default page fixture."""
    context = browser.new_context(
        base_url=BASE_URL, storage_state=auth_state["storage_state"]
    )
    session_storage = auth_state["session_storage"]
    init_script = "".join(
        f"window.sessionStorage.setItem({json.dumps(key)}, {json.dumps(value)});"
        for key, value in session_storage.items()
    )
    context.add_init_script(init_script)
    pg = context.new_page()
    yield pg
    context.close()


@pytest.fixture
def dashboard(page: Page) -> Page:
    """A page already sitting on the dashboard."""
    page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible()
    return page

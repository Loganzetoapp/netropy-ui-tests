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

# The appliance silently accepts and saves a testbed name longer than this,
# then permanently 502s on activate for that object — no validation at
# creation time, no maxlength on the wizard's name field (see project bugs
# memory, 2026-09-09). Any test that creates a testbed it's going to
# activate should call assert_activatable_name() on the name right after
# defining it, so a future violation fails fast and clearly at collection
# time instead of a mysterious 75s hang + 502 deep into the test.
MAX_ACTIVATABLE_TESTBED_NAME_LEN = 15


def assert_activatable_name(name: str) -> None:
    assert len(name) <= MAX_ACTIVATABLE_TESTBED_NAME_LEN, (
        f"Testbed name {name!r} is {len(name)} chars, over the "
        f"{MAX_ACTIVATABLE_TESTBED_NAME_LEN}-char limit this appliance "
        "silently accepts on save but then permanently 502s on activate "
        "for. Shorten it before this test tries to activate."
    )


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
def page(browser, auth_state, request, pytestconfig) -> Page:
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

    # pytest-playwright's own --screenshot/--output capture only wires up
    # through ITS OWN page/context fixtures (an ArtifactsRecorder that
    # attaches via context.on("page", ...) inside its own fixture chain) —
    # since this fixture overrides both, that mechanism is otherwise
    # entirely inert here despite pytest.ini's --screenshot only-on-failure
    # (confirmed 2026-09-10 while building the results dashboard: zero
    # screenshots had ever actually been written, for any failure, in this
    # suite's whole history). Reimplemented directly here, reusing the same
    # CLI options pytest-playwright itself uses. The path naming
    # (scripts/artifact_paths.slugify) is our own, not pytest-playwright's
    # python-slugify — collect_run.py reads it back using the same
    # function, so the two only need to agree with each other.
    screenshot_option = pytestconfig.getoption("--screenshot")
    rep_call = getattr(request.node, "rep_call", None)
    failed = rep_call.failed if rep_call is not None else True
    if screenshot_option == "on" or (failed and screenshot_option == "only-on-failure"):
        try:
            from scripts.artifact_paths import slugify

            output_dir = pathlib.Path(pytestconfig.getoption("--output"))
            test_dir = output_dir / slugify(request.node.nodeid)
            test_dir.mkdir(parents=True, exist_ok=True)
            status = "failed" if failed else "finished"
            pg.screenshot(
                path=str(test_dir / f"test-{status}-1.png"),
                full_page=bool(pytestconfig.getoption("--full-page-screenshot")),
            )
        except Exception:
            pass  # a screenshot is a nice-to-have — never fail teardown over one

    context.close()


@pytest.fixture
def dashboard(page: Page) -> Page:
    """A page already sitting on the dashboard."""
    page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible()
    return page


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Results dashboard wire-up: after every session, collect this run's
    results/junit.xml into results/history/<run-id>.json, then rebuild
    results/index.html from the full history — "pytest ... -> history
    written -> report rebuilt", zero extra steps.

    A conftest hook (rather than a separate wrapper script) so this fires
    for every invocation shape this suite actually uses — plain `pytest`,
    `python -m pytest`, from a Makefile target, from CI — without anyone
    having to remember to call a wrapper. trylast=True so this runs after
    pytest's own junitxml plugin (also a pytest_sessionfinish hook) has
    finished writing results/junit.xml; hook order across plugins isn't
    otherwise guaranteed, and reading before it's written would silently
    collect nothing or a stale run.

    Deliberately never lets a reporting failure affect the actual test
    run's outcome — this is best-effort bookkeeping bolted on after the
    fact, not part of the suite itself. See scripts/collect_run.py and
    scripts/build_report.py for the real logic.
    """
    try:
        from scripts import build_report, collect_run

        markers = session.config.getoption("markexpr", default="") or ""
        written = collect_run.collect(markers=markers)
        if written is not None:
            build_report.build()
    except Exception as exc:  # never fail the run over reporting
        print(f"\n[results dashboard] WARNING: history/report step failed: {exc}")

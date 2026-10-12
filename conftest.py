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
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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

# The page objects in pages/ hold every selector; the helpers below are
# thin shims kept so existing tests' imports keep working. New tests use
# pages/ (or the traffic_engine fixture) directly.
from pages import settings as _settings
from pages.dashboard_page import DashboardPage
from pages.errors import PortsBusyError, SystemBadStateError  # noqa: F401  (re-exported)
from pages.login_page import LoginPage
from pages.run_page import RunPage
from pages.testbed_editor_page import START_POPUP_TITLE, TestbedEditorPage  # noqa: F401
from pages.unit_health import UnitHealth

MAX_ACTIVATABLE_TESTBED_NAME_LEN = _settings.MAX_TESTBED_NAME_LEN


def assert_activatable_name(name: str) -> None:
    """The appliance saves a testbed name over 15 chars, then permanently
    502s on activate for it (project bugs, 2026-09-09): fail fast instead."""
    assert len(name) <= MAX_ACTIVATABLE_TESTBED_NAME_LEN, (
        f"Testbed name {name!r} is {len(name)} chars, over the "
        f"{MAX_ACTIVATABLE_TESTBED_NAME_LEN}-char limit this appliance "
        "silently accepts on save but then permanently 502s on activate "
        "for. Shorten it before this test tries to activate."
    )


def assert_unit_healthy(page: Page, context: str = "") -> None:
    UnitHealth(page).assert_healthy(context)


def start_testbed(page: Page, start_button=None, timeout: int = 90_000) -> None:
    TestbedEditorPage(page).start(start_button, timeout)


def testbed_tile(page: Page, name: str):
    return DashboardPage(page).testbed_entry(name)


def create_testbed(page: Page, name: str):
    return DashboardPage(page).create_testbed(name)


def open_editor(page: Page, name: str) -> None:
    DashboardPage(page).open_editor(name)


def enable_ports(page: Page, ports, rate: str = None, unit: str = "Gbps") -> None:
    TestbedEditorPage(page).enable_ports(ports, rate, unit)


def open_step(page: Page, number: int) -> None:
    TestbedEditorPage(page).open_step(number)


def set_addressing(page: Page, ports, ips, cidr: int) -> None:
    TestbedEditorPage(page).set_addressing(ports, ips, cidr)


def add_stream(page: Page, protocol: str, quantity: int = 1) -> None:
    TestbedEditorPage(page).add_stream(protocol, quantity)


def set_all_frame_sizes(page: Page, size: int) -> None:
    TestbedEditorPage(page).set_all_frame_sizes(size)


def set_stream_frame_size(page: Page, index: int, size: int) -> None:
    TestbedEditorPage(page).set_stream_frame_size(index, size)


def set_ramp(page: Page, up: int, hold: int, down: int) -> None:
    TestbedEditorPage(page).set_ramp(up, hold, down)


def wait_for_run_to_finish(page: Page, run_number: int = 1, timeout: int = 5 * 60_000):
    return RunPage(page).wait_for_run_to_finish(run_number, timeout)


def assert_run_passed(row) -> None:
    verdict = RunPage.verdict(row)
    assert verdict == "pass", f"run verdict {verdict!r}; saved run row: {row.inner_text()!r}"


def run_verdict(row) -> str:
    return RunPage.verdict(row)


def go_to_dashboard(page: Page) -> None:
    DashboardPage(page).open()


def remove_testbed(page: Page, name: str) -> None:
    DashboardPage(page).remove_testbed(name)


def _login(page: Page) -> None:
    """Log in through the UI (returns at once if the session is valid)."""
    LoginPage(page).login(url=BASE_URL)


@pytest.fixture(scope="session")
def auth_state(browser) -> dict:
    """Log in once per session and persist storage state + session storage."""
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    _login(page)
    # Run the whole suite against the product's Dark mode (topbar gear menu
    # -> "Dark mode") rather than its light-mode default. The toggle just
    # flips localStorage["tgen-theme"] between "light"/"dark" (confirmed by
    # inspecting it directly) with no server-side/account-level component,
    # so setting it here — before the storage_state() snapshot below — is
    # equivalent to clicking it, and every test's fresh context inherits it
    # for free via the same storage_state replay that already carries auth.
    page.evaluate("() => localStorage.setItem('tgen-theme', 'dark')")
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
    # NTG 5.0 defaults the Testbeds section to table view; every helper in
    # this suite scopes to card tiles (.tb-tile). Pin the user's own view
    # preference to cards — only when unset, so a test that flips the
    # Card/Table toggle mid-test isn't reverted on its next navigation.
    init_script += (
        "try{if(!localStorage.getItem('tgen-tb-view'))"
        "localStorage.setItem('tgen-tb-view','cards')}catch(e){}"
    )
    context.add_init_script(init_script)

    # Tracing is only captured for runs the web dashboard triggers (see
    # webapp/runner.py, which sets NETROPY_WEBAPP_BATCH_ID) — the existing
    # CLI-driven suite's disk usage and behavior stay exactly as they are.
    capture_trace = bool(os.environ.get("NETROPY_WEBAPP_BATCH_ID"))
    if capture_trace:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

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

    # retain-on-failure: only keep the trace file for a failed run; still
    # call stop() either way to end the tracing session cleanly.
    if capture_trace:
        try:
            from scripts.artifact_paths import slugify

            output_dir = pathlib.Path(pytestconfig.getoption("--output"))
            test_dir = output_dir / slugify(request.node.nodeid)
            if failed:
                test_dir.mkdir(parents=True, exist_ok=True)
                context.tracing.stop(path=str(test_dir / "trace.zip"))
            else:
                context.tracing.stop()
        except Exception:
            pass

    context.close()


@pytest.fixture
def dashboard(page: Page) -> Page:
    """A page already sitting on the dashboard."""
    page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible()
    wait_for_testbeds_loaded(page)
    return page


@pytest.fixture
def wan_page(browser) -> Page:
    """A logged-in page on the WAN emulator chained between NTG Port 3 and
    Port 4 (see wan_emulator.py). Its own browser context, so it never
    shares state with the NTG `page`. Skips when WAN_EMULATOR_URL is unset."""
    import wan_emulator

    if not wan_emulator.WAN_URL:
        pytest.skip("WAN_EMULATOR_URL not set in .env")
    context = browser.new_context(base_url=wan_emulator.WAN_URL)
    pg = context.new_page()
    wan_emulator.login(pg)
    yield pg
    context.close()


@pytest.fixture
def run_metrics(request):
    """A RunMetrics (run_metrics.py) for the test to fill in. Written to
    results/metrics/ on teardown, pass or fail, and linked into the run
    history through the junit property `metrics`."""
    from run_metrics import RunMetrics
    from scripts.artifact_paths import slugify

    metrics = RunMetrics(request.node.nodeid)
    yield metrics
    path = metrics.write(slugify(request.node.nodeid))
    request.node.user_properties.append(
        ("metrics", str(path.relative_to(pathlib.Path(__file__).parent)))
    )


@pytest.fixture
def traffic_engine(dashboard: Page, run_metrics):
    """The high-level library (pages/traffic_engine.py) on a logged-in
    dashboard, recording onto this test's summary sheet. Teardown removes
    every testbed it created, and only those. Ports held by someone else
    make the test skip (see pytest_runtest_makereport), never steal."""
    from pages.traffic_engine import TrafficEngine

    engine = TrafficEngine(dashboard, run_metrics)
    try:
        yield engine
    finally:
        engine.cleanup()


def wait_for_testbeds_loaded(page: Page) -> None:
    DashboardPage(page).wait_loaded()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase's report as item.rep_<phase> (the page fixture's
    screenshot/trace logic reads rep_call — nothing set it before, so it
    treated every test as failed), and tag SystemBadStateError failures
    with a `failure_kind=system` junit property for the run history."""
    outcome = yield
    rep = outcome.get_result()
    if call.excinfo is not None and call.excinfo.errisinstance(PortsBusyError):
        # Shared box: someone else holds the ports. Not a failure; skip.
        rep.outcome = "skipped"
        rep.longrepr = (str(item.fspath), item.location[1], f"Skipped: {call.excinfo.value}")
    setattr(item, f"rep_{rep.when}", rep)
    if call.excinfo is not None and call.excinfo.errisinstance(SystemBadStateError):
        # On the item, not this report: junitxml writes properties from the
        # teardown report, which copies item.user_properties when created.
        item.user_properties.append(("failure_kind", "system"))


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

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


class SystemBadStateError(AssertionError):
    """The unit itself is unhealthy (controller/unit offline, recovery
    mode, a disconnected testbed, or a run whose results were lost) — as
    opposed to a test finding wrong behaviour on a healthy unit. Raising
    this marks the test as a SYSTEM failure in junit, run history and the
    dashboard (see pytest_runtest_makereport below), per the 2026-09-30
    request to report these separately from ordinary test failures."""


# Top-bar health indicators (polled by the app every 5 s from the
# Controller's health check): any of these means the unit isn't healthy.
_UNHEALTHY_TOPBAR = ("offline", "controller offline", "RECOVERY")


def assert_unit_healthy(page: Page, context: str = "") -> None:
    """UI-only health check: back on the dashboard, after one full health
    poll, the top bar must read "online" with no offline/recovery
    indicator, and no testbed may be stuck "disconnected". Raises
    SystemBadStateError (not a plain assertion) when the unit is unhealthy."""
    go_to_dashboard(page)
    page.wait_for_timeout(6_000)  # let at least one 5 s health poll land
    problems = []
    for text in _UNHEALTHY_TOPBAR:
        if page.get_by_text(text, exact=True).count():
            problems.append(f"top bar shows {text!r}")
    if page.get_by_text("online", exact=True).count() == 0:
        problems.append("top bar never shows 'online'")
    testbeds = page.locator(".card").filter(has_text="Testbeds")
    if testbeds.get_by_text("disconnected", exact=True).count():
        problems.append("a testbed is in the 'disconnected' state")
    if problems:
        where = f" ({context})" if context else ""
        raise SystemBadStateError(f"Unit unhealthy{where}: " + "; ".join(problems))


# NTG 5.0's default "auto" activation mode: Start on an inactive testbed
# (dashboard tile or editor bar) opens this confirm, then Continue runs
# deactivate-conflicts -> activate -> start in one go. The dialog has no
# role="dialog"/aria-labelledby, so it's found by its title text.
START_POPUP_TITLE = "Testbed is Inactive"


def start_testbed(page: Page, start_button=None, timeout: int = 90_000) -> None:
    """Click Start, confirm the 5.0 "Testbed is Inactive" popup, and wait
    for traffic to actually be running (a Stop button appears).

    `start_button` defaults to the editor bar's Start; pass a tile's
    Start button to start from the dashboard. If the unit rejects the
    start, the app shows the error only as a toast — that text is put in
    the assertion message so a failed start says why."""
    button = start_button or page.get_by_role("button", name="Start", exact=True)
    button.click()
    title = page.get_by_text(START_POPUP_TITLE, exact=True)
    # Already active + synced testbeds skip the popup and start directly.
    try:
        title.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        pass
    else:
        page.get_by_role("button", name="Continue").click()
        expect(title).to_be_hidden()
    stop = page.get_by_role("button", name="Stop", exact=True).first
    try:
        expect(stop).to_be_visible(timeout=timeout)
    except AssertionError as exc:
        toasts = page.locator(".toast").all_inner_texts()
        raise AssertionError(
            f"Traffic never started after Start → Continue. On-screen toasts: {toasts!r}"
        ) from exc


# Shown on Statistics when the testbed is active but nothing is running.
# 5.0 can accept Start (both API calls 200, Stop briefly shown), look live
# for a while, then fall back to this with no saved run and no error —
# seen 4/4 for the NTP lifecycle test, 2026-10-01.
_ARMED_IDLE = re.compile(r"Ports are armed and idle", re.I)


def testbed_tile(page: Page, name: str):
    """A testbed's dashboard card, matched on its exact name (so "T10-A"
    never also matches "T10-AB")."""
    return page.locator(".tb-tile").filter(has=page.get_by_text(name, exact=True))


def create_testbed(page: Page, name: str):
    """Create an inactive Traffic Engine draft from the dashboard; returns its tile."""
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(name)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    tile = testbed_tile(page, name)
    expect(tile).to_have_count(1, timeout=10_000)
    return tile


def open_editor(page: Page, name: str) -> None:
    testbed_tile(page, name).get_by_role("button", name="Edit").click()
    expect(page.get_by_role("heading", name="Ports")).to_be_visible(timeout=15_000)


def _port_row(page: Page, port: str):
    # Anchored: "Port 3" must not also match the Port 4 row, whose text
    # lists "Port 3" as its peer.
    return page.get_by_role("row", name=re.compile(rf"^{re.escape(port)}\b"))


def enable_ports(page: Page, ports, rate: str = None, unit: str = "Gbps") -> None:
    """Editor step 1: turn on USE for each port (two ports auto-peer) and
    optionally set every one's line rate."""
    for port in ports:
        row = _port_row(page, port)
        use = row.get_by_role("checkbox").first
        if not use.is_checked():
            # The checkbox is visually replaced by a toggle track; click its wrapper.
            use.locator("xpath=..").click()
        expect(use).to_be_checked()
        if rate is not None:
            row.get_by_role("combobox").last.select_option(unit)
            field = row.get_by_role("spinbutton")
            field.fill(str(rate))
            field.press("Tab")
            expect(field).to_have_value(str(rate))


def open_step(page: Page, number: int) -> None:
    """Expand an editor step by its number (1 Ports … 4 Traffic and Load
    Profile). The header toggles, so only click it when collapsed."""
    header = page.get_by_role("button", name=re.compile(rf"^{number} ")).first
    if header.get_attribute("aria-expanded") != "true":
        header.click()
    expect(header).to_have_attribute("aria-expanded", "true")


def set_addressing(page: Page, ports, ips, cidr: int) -> None:
    """Editor step 2 (5.0's default Table view): give each port a source
    IP on a /`cidr` subnet and point each port's destination IP at its
    peer's source IP. `ports` are port numbers in pair order, e.g. (3, 4),
    `ips` the matching source IPs. Only for a two-port pair."""
    open_step(page, 2)
    rows = [page.get_by_role("row", name=re.compile(rf"^{n}\s")) for n in ports]
    for row, ip in zip(rows, ips):
        src = row.get_by_role("textbox", name="10.1.0.10")
        src.fill(ip)
        src.press("Tab")
        row.get_by_role("combobox").first.select_option(label=f"/{cidr}")
    for row, peer_ip in zip(rows, reversed(ips)):
        dst = row.get_by_role("textbox", name="auto").first
        dst.fill(peer_ip)
        dst.press("Tab")
    for row, ip, peer_ip in zip(rows, ips, reversed(ips)):
        expect(row.get_by_role("textbox", name="10.1.0.10")).to_have_value(ip)
        expect(row.get_by_role("textbox", name="auto").first).to_have_value(peer_ip)


def add_stream(page: Page, protocol: str, quantity: int = 1) -> None:
    """Editor step 3: add `quantity` streams of `protocol` (the Add Stream
    modal's list button, e.g. "UDP", "TCP", "ICMP", "DNS", "HTTP")."""
    open_step(page, 3)
    # The per-row delete icon has no accessible name, only a data-tip.
    rows = page.locator("tr").filter(has=page.locator('span[data-tip="Delete stream"]'))
    before = rows.count()
    page.get_by_role("button", name="✚ Add Stream").click()
    page.get_by_role("button", name=re.compile(rf"^{re.escape(protocol)}( WIP)?$")).first.click()
    if quantity != 1:
        page.get_by_label(re.compile("Quantity", re.I)).fill(str(quantity))
    page.get_by_role("button", name="Add stream", exact=True).click()
    expect(rows).to_have_count(before + quantity)


def set_all_frame_sizes(page: Page, size: int) -> None:
    """Editor step 3: the "Frame size — apply to all" control."""
    open_step(page, 3)
    apply = page.get_by_role("button", name="Apply to all", exact=True)
    # The size field sits right beside the button, in the same container.
    apply.locator("xpath=..").get_by_role("spinbutton").fill(str(size))
    apply.click()
    rows = page.locator("tr").filter(has=page.locator('span[data-tip="Delete stream"]'))
    for i in range(rows.count()):
        expect(rows.nth(i).get_by_role("spinbutton")).to_have_value(str(size))


def set_stream_frame_size(page: Page, index: int, size: int) -> None:
    """Editor step 3: frame size of the `index`-th stream row (0-based,
    in the order streams were added)."""
    open_step(page, 3)
    rows = page.locator("tr").filter(has=page.locator('span[data-tip="Delete stream"]'))
    field = rows.nth(index).get_by_role("spinbutton")
    field.fill(str(size))
    field.press("Tab")
    expect(field).to_have_value(str(size))


def set_ramp(page: Page, up: int, hold: int, down: int) -> None:
    """Editor step 4: enable the load ramp and set its phases (seconds), so
    the run ends on its own after up + hold + down."""
    open_step(page, 4)
    disabled = page.get_by_text("Disabled — traffic runs at full rate")
    if disabled.count():
        page.locator("div", has=disabled).last.locator(".toggle .track").click()
    for label, secs in (("Ramp up", up), ("Hold time", hold), ("Ramp down", down)):
        field = page.locator(".fg", has_text=label).locator('input[type="number"]').first
        field.fill(str(secs))
        field.press("Tab")
    expect(page.get_by_text(re.compile(r"Total run time"))).to_contain_text(f"= {up + hold + down}s")


def wait_for_run_to_finish(page: Page, run_number: int = 1, timeout: int = 5 * 60_000):
    """After start_testbed() from the editor (which lands on Statistics):
    block until run #`run_number` is saved to Test Reports — i.e. the run
    ended — and return that table row. A fresh testbed's first run is #1.

    Saved rows are the reliable end signal; the Stop button is not (the
    editor -> Statistics hand-off briefly shows neither Start nor Stop)."""
    expect(page.get_by_role("heading", name=re.compile(r"^Statistics"))).to_be_visible(
        timeout=30_000
    )
    # Row text runs straight into the badge ("#1LATEST…"), so no \b here.
    row = page.get_by_role("row").filter(has_text=re.compile(rf"^\s*#{run_number}(?!\d)"))
    idle = page.get_by_text(_ARMED_IDLE)
    idle_ms, waited = 0, 0
    while row.count() != 1:
        if waited >= timeout:
            raise AssertionError(
                f"Run #{run_number} was not saved within {timeout // 1000}s. "
                f"{_stats_state(page)}"
            )
        # Statistics falls back to "armed and idle" once nothing is running;
        # staying there with no saved run means the run ended and its stats
        # were lost (the engineer's "no new run record" case).
        idle_ms = idle_ms + 1_000 if idle.count() else 0
        if idle_ms >= 15_000:
            raise SystemBadStateError(
                f"Run #{run_number} ended but was never saved (stats lost). "
                f"{_stats_state(page)}"
            )
        page.wait_for_timeout(1_000)
        waited += 1_000
    return row


def assert_run_passed(row) -> None:
    """Assert a Test Reports row's RESULT is pass; on failure the message
    carries the whole row (avg TX/RX, loss %, duration, end reason) so a
    FAIL verdict says why without re-running."""
    verdict = run_verdict(row)
    assert verdict == "pass", f"run verdict {verdict!r}; saved run row: {row.inner_text()!r}"


def _stats_state(page: Page) -> str:
    header = page.locator("h1, h2").first.locator("xpath=..").inner_text()[:300]
    status = page.get_by_text(re.compile(r"^LIVE ·|Ready to start|armed", re.I)).all_inner_texts()
    toasts = page.locator(".toast").all_inner_texts()
    return f"Header: {header!r}; status text: {status!r}; toasts: {toasts!r}"


def run_verdict(row) -> str:
    """The RESULT cell of a Test Reports row, lowercased ("pass"/"fail")."""
    cell = row.get_by_text(re.compile(r"^(pass|fail)$", re.I))
    expect(cell).to_be_visible(timeout=30_000)
    return cell.inner_text().strip().lower()


def go_to_dashboard(page: Page) -> None:
    """From anywhere in the app, back to a loaded dashboard. Uses the SPA's
    own button (a hard reload mid-run has crashed teardown before) and
    discards unsaved edits if asked."""
    back = page.get_by_role("button", name="← Dashboard")
    if back.is_visible():
        back.click()
        discard = page.get_by_role("button", name="Discard", exact=True)
        try:
            discard.wait_for(state="visible", timeout=1_500)
            discard.click()
        except PlaywrightTimeoutError:
            pass
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20_000)
    wait_for_testbeds_loaded(page)


def remove_testbed(page: Page, name: str) -> None:
    """Teardown: stop, deactivate (frees its ports) and delete testbed
    `name` if it exists. Only ever touches that one testbed."""
    go_to_dashboard(page)
    tile = testbed_tile(page, name)
    if tile.count() == 0:
        return
    stop = tile.get_by_role("button", name="Stop", exact=True)
    if stop.count():
        stop.click()
        expect(stop).to_have_count(0, timeout=30_000)
    tile.locator('[data-tip="Delete"] button').click()
    # Active testbeds get "Deactivate / Delete" first; deactivate so the
    # ports are released cleanly, then delete the inactive draft.
    deactivate = page.get_by_role("button", name="Deactivate", exact=True)
    try:
        deactivate.wait_for(state="visible", timeout=2_000)
    except PlaywrightTimeoutError:
        pass
    else:
        deactivate.click()
        # The dialog closes once the deactivate call has finished.
        expect(deactivate).to_be_hidden(timeout=30_000)
        tile.locator('[data-tip="Delete"] button').click()
    page.get_by_role("button", name="Delete", exact=True).last.click()
    expect(tile).to_have_count(0, timeout=20_000)


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


def wait_for_testbeds_loaded(page: Page) -> None:
    """Block until the Testbeds section has fetched its list. On NTG 5.0
    the header reads "… " while loading and "N saved · M active" once
    done; Port Status renders well before that, so any instant check
    like `tile.count()` right after landing races the list fetch and
    sees zero cards."""
    expect(
        page.locator(".card").filter(has_text="Testbeds").get_by_text(
            re.compile(r"^\d+ saved · \d+ active$")
        )
    ).to_be_visible(timeout=20_000)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase's report as item.rep_<phase> (the page fixture's
    screenshot/trace logic reads rep_call — nothing set it before, so it
    treated every test as failed), and tag SystemBadStateError failures
    with a `failure_kind=system` junit property for the run history."""
    outcome = yield
    rep = outcome.get_result()
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

"""UI helpers for the Netropy WAN Emulator chained between the NTG's ports.

Lab wiring (2026-09-30 meeting): NTG Port 3 <-> emulator Engine 2
(emulator ports 3/4) <-> NTG Port 4. The emulator is a separate box
(Netropy 10G2; .213 runs firmware 5.1.5) with its own React UI, driven here the
same way the NTG is: through the UI in its own browser context.

How traffic gets impaired, from the emulator's own model:
  * An engine bridges two ports. With Emulation OFF it is a plain bypass.
  * A *path* holds the impairments (delay, loss, ... per direction) plus
    an access-link bandwidth on each side.
  * Each port's *Default Action* (Bypass / Drop / <a path>) decides where
    traffic that matches no endpoint goes. Pointing both ports' Default
    Action at a path sends all NTG traffic through it, so no endpoints or
    rules are needed.
  * The emulator refuses to delete a path that is still a port's Default
    Action ("Path is default action for Port N"), so teardown order is:
    Emulation off -> Default Actions back -> delete the path.

Selector notes (for the PR description, per CLAUDE.md): the emulator UI
has almost no accessible names. Path-form controls are unlabeled
<select>/<input> elements that only carry a `name` like
"wan/source-to-destination/delay/method", the Default Action selects are
named "port-a"/"port-b", and the Paths "+" button is an icon inside an
<a href="/path/create">. These attribute selectors are the only stable
handles until the emulator gets labels or data-testids.
"""
import contextlib
import os
import re

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

WAN_URL = os.environ.get("WAN_EMULATOR_URL", "").rstrip("/")
WAN_USER = os.environ.get("WAN_EMULATOR_USER", "")
WAN_PASS = os.environ.get("WAN_EMULATOR_PASS", "")

# Emulator engine that sits between NTG Port 3 and Port 4.
NTG_ENGINE = "Engine 2"

# A new path's access links default to 128 Kbps, which would throttle any
# NTG run to nothing. Delay-only paths open them up to the port speed.
WIDE_OPEN_GBPS = 10

_DIRECTIONS = ("source-to-destination", "destination-to-source")
_ACCESS_LINKS = ("source/outbound", "destination/outbound")


def login(page: Page) -> None:
    page.goto("/login")
    page.get_by_role("textbox").first.fill(WAN_USER)
    page.locator("input[type=password]").fill(WAN_PASS)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Topology")).to_be_visible(timeout=20_000)


def open_engine(page: Page, engine: str = NTG_ENGINE) -> None:
    """Select an engine tab and return to its Topology view."""
    page.goto("/")
    page.get_by_role("tab", name=engine).click()
    expect(page.locator(".default-action-wrapper")).to_be_visible()


def emulation_toggle(page: Page):
    return page.locator("label.emulation input[type=checkbox]")


def set_emulation(page: Page, on: bool) -> None:
    """Turn the current engine's Emulation switch on or off, and confirm
    the emulator saved it (same async-save caveat as set_default_actions)."""
    for _ in range(5):
        if emulation_toggle(page).is_checked() == on:
            return
        # react-toggle hides the real checkbox under its track.
        page.locator("label.emulation .react-toggle").click()
        page.wait_for_timeout(3_000)
        open_engine(page)
    raise AssertionError(f"Emulator Emulation switch never saved as {'on' if on else 'off'}")


def default_actions(page: Page) -> dict:
    """Current Default Action of both engine ports, as option labels."""
    return {
        name: page.locator(f"select[name='{name}']").evaluate(
            "e => e.options[e.selectedIndex].text"
        )
        for name in ("port-a", "port-b")
    }


def set_default_actions(page: Page, labels) -> None:
    """Set both engine ports' Default Action and wait until the emulator
    has saved it. `labels` is one label for both ports ("Bypass", "Drop",
    or a path name) or a {"port-a": ..., "port-b": ...} dict.

    Each select change is pushed to the box asynchronously, and two
    changes in quick succession clobber each other (seen 2026-10-01: both
    set, only port-a saved), and reloading right after a change aborts its
    save. So ports are changed one at a time, each given a few seconds to
    save, then checked after a reload and retried if it didn't stick. Without the wait, deleting a
    path right after un-assigning it is refused ("Path is default action
    for Port N")."""
    if isinstance(labels, str):
        labels = {"port-a": labels, "port-b": labels}
    for port, label in labels.items():
        if default_actions(page)[port] == label:
            continue
        for _ in range(5):
            page.locator(f"select[name='{port}']").select_option(label=label)
            # Navigating away too soon aborts the save; let it land first.
            page.wait_for_timeout(3_000)
            open_engine(page)
            if default_actions(page)[port] == label:
                break
        else:
            raise AssertionError(
                f"Emulator Default Action for {port} never saved as {label!r}; "
                f"still {default_actions(page)}"
            )


def path_link(page: Page, name: str):
    return page.locator(".list-group.paths").get_by_text(name, exact=True)


def create_delay_path(page: Page, name: str, delay_ms: float) -> None:
    """Create a delay-only path on the current engine: constant `delay_ms`
    in both directions, nothing else, access links wide open."""
    page.locator("a[href='/path/create']").click()
    page.get_by_placeholder("Enter Path Name...").fill(name)
    for link in _ACCESS_LINKS:
        page.locator(f"select[name='{link}/bandwidth/metric']").select_option("Gbps")
        rate = page.locator(f"[name='{link}/bandwidth/rate']")
        rate.fill(str(WIDE_OPEN_GBPS))
        rate.press("Tab")
    for direction in _DIRECTIONS:
        page.locator(f"select[name='wan/{direction}/delay/method']").select_option("constant")
        latency = page.locator(f"[name='wan/{direction}/delay/constant/latency']")
        latency.fill(str(delay_ms))
        latency.press("Tab")
        expect(latency).to_have_value(str(delay_ms))
    page.get_by_role("button", name="Create Path").click()
    expect(path_link(page, name)).to_be_visible(timeout=15_000)


def delete_path(page: Page, name: str) -> None:
    """Delete path `name` if it exists. It must no longer be a Default
    Action, or the emulator refuses."""
    link = path_link(page, name)
    if link.count() == 0:
        return
    # Clicking the name opens the path's stats; editing and Delete Path
    # live behind the row's gear icon (an unlabeled <a href=".../manage">).
    row = page.locator(".list-group.paths .list-group-item").filter(
        has=page.get_by_text(name, exact=True)
    )
    row.locator("a[href$='/manage']").click()
    # Accept a native confirm() if there is one (Playwright would dismiss it).
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete Path").click()
    confirm = page.get_by_role("button", name=re.compile(r"^(Delete|Remove|OK|Yes)$"))
    try:
        confirm.first.wait_for(state="visible", timeout=2_000)
    except PlaywrightTimeoutError:
        pass
    else:
        confirm.first.click()
    open_engine(page)
    expect(path_link(page, name)).to_have_count(0, timeout=15_000)


@contextlib.contextmanager
def delay_between_ntg_ports(page: Page, name: str, delay_ms: float):
    """Put a constant `delay_ms` (each way) between NTG Port 3 and Port 4
    for the duration of the block, then put Engine 2 back exactly as it
    was (Emulation state and both Default Actions)."""
    open_engine(page)
    was_on = emulation_toggle(page).is_checked()
    before = default_actions(page)
    # A path with this name left over from an aborted run would collide.
    if name in before.values():
        set_emulation(page, False)
        set_default_actions(page, "Bypass")
    delete_path(page, name)
    try:
        create_delay_path(page, name, delay_ms)
        open_engine(page)
        set_default_actions(page, name)
        set_emulation(page, True)
        yield
    finally:
        open_engine(page)
        set_emulation(page, False)
        set_default_actions(
            page, {port: "Bypass" if label == name else label for port, label in before.items()}
        )
        delete_path(page, name)
        open_engine(page)
        set_emulation(page, was_on)

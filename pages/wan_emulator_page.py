"""The WAN emulator (Netropy 10G2) as a page object. Every emulator selector
lives here; docs/wan-emulator-reference.md maps the whole UI.

How traffic gets impaired, from the emulator's own model:
  * An engine bridges two ports. With Emulation off it is a plain bypass.
    Engine 2 (emulator ports 3/4) sits between NTG Port 3 and Port 4.
  * A *path* holds the impairments (delay, loss, ... per direction) plus an
    access-link bandwidth on each side.
  * Each port's *Default Action* (Bypass / Drop / <path>) decides where
    traffic matching no endpoint goes. Pointing both at one path sends all
    NTG traffic through it, so no endpoints or rules are needed.
  * A path can't be deleted while it is a Default Action, so teardown is:
    Emulation off -> Default Actions back -> delete the path.

Selector notes (for the PR description, per CLAUDE.md): no emulator form
control has an accessible name. Path-form controls carry only a `name`
("wan/source-to-destination/delay/method"), the Default Action selects are
named "port-a"/"port-b", and the Paths "+" and per-path gear are icon-only
links. These attribute selectors are the only stable handles until the
emulator gets labels or data-testids.

Added 2026-10-19 for T18-T21 and checked by tests/t0_library/
test_t0_wan_library.py (no traffic): edit_path, create_path_from_preset
(a hover menu) and the endpoint methods.
"""
import contextlib
import re
from dataclasses import dataclass
from typing import Dict

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from pages import settings
from pages.base_page import BasePage
from pages.errors import PortsBusyError
from pages.wan_path_spec import EndpointSpec, WanPathSpec

# Default Action and Emulation changes save asynchronously, with no
# feedback. Reloading too soon aborts the save, and two changes in quick
# succession clobber each other (seen 2026-10-01). One change at a time,
# then this long before reading it back.
_SAVE_SETTLE_MS = 3_000
_SAVE_ATTEMPTS = 5
_PORTS = ("port-a", "port-b")


@dataclass
class EngineState:
    """An engine's switch settings: Emulation and both Default Actions."""
    emulation: bool
    actions: Dict[str, str]   # {"port-a": label, "port-b": label}

    @property
    def idle(self) -> bool:
        return not self.emulation and set(self.actions.values()) == {"Bypass"}


class WanEmulatorPage(BasePage):
    ENGINE = "Engine 2"   # emulator ports 3/4 = NTG Port 3 <-> Port 4
    ENGINE_INDEX = 2      # the same engine, as the API numbers it

    def __init__(self, page: Page):
        super().__init__(page)

    # --- session / navigation -----------------------------------------
    def login(self) -> None:
        page = self.page
        page.goto("/login")
        page.get_by_role("textbox").first.fill(settings.WAN_USER)
        page.locator("input[type=password]").fill(settings.WAN_PASS)
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_text("Topology")).to_be_visible(timeout=20_000)

    def open_engine(self, engine: str = None) -> None:
        """Select an engine tab and land on its Topology view."""
        self.page.goto("/")
        self.page.get_by_role("tab", name=engine or self.ENGINE).click()
        expect(self.page.locator(".default-action-wrapper")).to_be_visible()

    # --- engine state ---------------------------------------------------
    def _emulation_toggle(self):
        return self.page.locator("label.emulation input[type=checkbox]")

    def emulation_on(self) -> bool:
        return self._emulation_toggle().is_checked()

    def set_emulation(self, on: bool) -> None:
        """Set (not toggle) Emulation, and confirm the box saved it."""
        for _ in range(_SAVE_ATTEMPTS):
            if self.emulation_on() == on:
                return
            # react-toggle hides the real checkbox under its track.
            self.page.locator("label.emulation .react-toggle").click()
            self.page.wait_for_timeout(_SAVE_SETTLE_MS)
            self.open_engine()
        raise AssertionError(f"Emulation never saved as {'on' if on else 'off'}")

    def default_actions(self) -> dict:
        """{"port-a": label, "port-b": label}: Bypass, Drop or a path name."""
        return {
            port: self.page.locator(f"select[name='{port}']").evaluate(
                "e => e.options[e.selectedIndex].text"
            )
            for port in _PORTS
        }

    def set_default_actions(self, labels) -> None:
        """Set both ports' Default Action. `labels` is one label for both,
        or {"port-a": ..., "port-b": ...}. Ports are changed one at a time
        and read back after a reload; see _SAVE_SETTLE_MS."""
        if isinstance(labels, str):
            labels = dict.fromkeys(_PORTS, labels)
        for port, label in labels.items():
            for _ in range(_SAVE_ATTEMPTS):
                if self.default_actions()[port] == label:
                    break
                self.page.locator(f"select[name='{port}']").select_option(label=label)
                self.page.wait_for_timeout(_SAVE_SETTLE_MS)
                self.open_engine()
            else:
                raise AssertionError(
                    f"Default Action for {port} never saved as {label!r}; "
                    f"still {self.default_actions()}"
                )

    def state(self) -> EngineState:
        return EngineState(self.emulation_on(), self.default_actions())

    def make_idle(self) -> None:
        """Emulation off, then both Default Actions to Bypass (the order
        that never leaves traffic on a half-configured path)."""
        self.set_emulation(False)
        self.set_default_actions("Bypass")

    def require_idle(self, own_path: str = None) -> None:
        """The engine is ours to use: Emulation off and both ports on
        Bypass. A Default Action pointing at `own_path` is a leftover from
        one of our own aborted runs and is cleaned up; anything else means
        someone else is using the engine, and the test is skipped."""
        actions = self.default_actions()
        if own_path and own_path in actions.values():
            self.set_emulation(False)
            self.set_default_actions("Bypass")
            actions = self.default_actions()
        if self.emulation_on() or set(actions.values()) != {"Bypass"}:
            raise PortsBusyError(
                f"WAN emulator {self.ENGINE} is in use: emulation "
                f"{'on' if self.emulation_on() else 'off'}, default actions {actions}"
            )

    # --- paths ----------------------------------------------------------
    def _path_link(self, name: str):
        return self.page.locator(".list-group.paths").get_by_text(name, exact=True)

    def create_path(self, spec: WanPathSpec) -> None:
        """Create the path described by `spec` on the current engine."""
        page = self.page
        page.locator("a[href='/path/create']").click()
        page.get_by_placeholder("Enter Path Name...").fill(spec.name)
        self._fill(spec.form_fields())
        page.get_by_role("button", name="Create Path").click()
        expect(self._path_link(spec.name)).to_be_visible(timeout=15_000)

    def _fill(self, values: Dict[str, str]) -> None:
        """Type {form control name: value} into the open form, in order
        (method selects come first: they reveal their value inputs)."""
        for key, value in values.items():
            control = self.page.locator(f"[name='{key}']")
            kind = control.evaluate("e => e.tagName === 'SELECT' ? 'select' : e.type")
            if kind == "checkbox":
                control.set_checked(value == "true")
                continue
            if kind == "select":
                control.select_option(value)
            else:
                control.fill(value)
                control.press("Tab")
            expect(control).to_have_value(value)

    def create_path_from_preset(self, name: str, group: str, preset: str) -> None:
        """Create path `name` from a built-in preset. The folder icon right
        of the name box opens a menu of groups (Cellular / Wi-Fi /
        Satellite / AWS / Cable / SD-WAN); each opens its items on *hover*
        (clicking a group closes the menu). `preset` is the item's exact
        text, e.g. "4G LTE", "GEO", "802.11n" (mapped 2026-10-19)."""
        page = self.page
        page.locator("a[href='/path/create']").click()
        name_box = page.get_by_placeholder("Enter Path Name...")
        name_box.locator("xpath=following::button[1]").click()
        menu = page.locator(".dropright").filter(has=page.locator("label").get_by_text(group, exact=True))
        menu.locator(".hover-dropdown").hover()
        menu.locator(".dropdown-item").get_by_text(preset, exact=True).click()
        # Fill the name last: picking a preset may overwrite it.
        name_box.fill(name)
        page.get_by_role("button", name="Create Path").click()
        expect(self._path_link(name)).to_be_visible(timeout=15_000)

    def _open_manage(self, name: str) -> None:
        """A path's own page, behind its row's gear icon (an unlabelled
        <a href=".../manage">); clicking the name opens its stats instead."""
        row = self.page.locator(".list-group.paths .list-group-item").filter(
            has=self.page.get_by_text(name, exact=True)
        )
        row.locator("a[href$='/manage']").click()

    def edit_path(self, spec: WanPathSpec) -> None:
        """Change existing path `spec.name` to `spec` with Apply Changes.
        Works while traffic flows through it (T19b). The save is
        asynchronous; callers confirm it through the API."""
        self.open_engine()
        self._open_manage(spec.name)
        self._fill(spec.form_fields())
        self.page.get_by_role("button", name="Apply Changes").click()

    def delete_path(self, name: str) -> None:
        """Delete path `name` if it exists. It must not be a Default Action."""
        if self._path_link(name).count() == 0:
            return
        page = self.page
        self._open_manage(name)
        # Accept a native confirm() if there is one (Playwright would dismiss it).
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Delete Path").click()
        self._confirm_if_asked()
        self.open_engine()
        expect(self._path_link(name)).to_have_count(0, timeout=15_000)

    def _confirm_if_asked(self) -> None:
        confirm = self.page.get_by_role("button", name=re.compile(r"^(Delete|Remove|OK|Yes)$"))
        try:
            confirm.first.wait_for(state="visible", timeout=2_000)
        except PlaywrightTimeoutError:
            pass
        else:
            confirm.first.click()

    # --- endpoints ------------------------------------------------------
    def _endpoint_row(self, label: str):
        # Endpoints are listed under "Endpoints N" like paths, one
        # .list-group-item each; labels never equal a path's (EndpointSpec).
        return self.page.locator(".list-group-item").filter(
            has=self.page.get_by_text(label, exact=True))

    def _endpoint_link(self, label: str):
        return self._endpoint_row(label)

    def create_endpoint(self, spec: EndpointSpec) -> None:
        """Create endpoint `spec` on the current engine; its path must exist.
        The form ("Create Endpoint") offers this engine's two ports, TCP/UDP,
        and an action select whose options are the paths by label."""
        page = self.page
        page.locator("a[href='/endpoint/create']").click()
        self._fill(spec.form_fields())
        page.locator("select[name='action']").select_option(label=spec.path)
        page.get_by_role("button", name="Create Endpoint").click()
        # Leaving the page before the save lands loses it, as with paths.
        expect(page).not_to_have_url(re.compile(r"/endpoint/create"), timeout=15_000)
        self.open_engine()
        expect(self._endpoint_row(spec.label)).to_be_visible(timeout=15_000)

    def delete_endpoint(self, label: str) -> None:
        """Delete endpoint `label` if it exists (the same gear-page flow as
        a path)."""
        if self._endpoint_link(label).count() == 0:
            return
        page = self.page
        page.once("dialog", lambda dialog: dialog.accept())
        self._endpoint_row(label).locator("a[href$='/manage']").click()
        page.get_by_role("button", name=re.compile(r"^Delete")).click()
        self._confirm_if_asked()
        self.open_engine()
        expect(self._endpoint_link(label)).to_have_count(0, timeout=15_000)

    @contextlib.contextmanager
    def path_created(self, spec: WanPathSpec):
        """`spec` exists as a path (not applied to traffic) for the block,
        then is deleted. For checking the form without touching traffic."""
        self.open_engine()
        self.delete_path(spec.name)
        try:
            self.create_path(spec)
            yield
        finally:
            self.open_engine()
            self.delete_path(spec.name)

    @contextlib.contextmanager
    def applied(self, spec: WanPathSpec):
        """All NTG Port 3 <-> 4 traffic goes through `spec` for the block.
        Requires an idle engine (see require_idle) and leaves it idle."""
        self.open_engine()
        self.require_idle(own_path=spec.name)
        with self.path_created(spec):
            try:
                self.open_engine()
                self.set_default_actions(spec.name)
                self.set_emulation(True)
                yield
            finally:
                self.open_engine()
                self.set_emulation(False)
                self.set_default_actions("Bypass")

    @contextlib.contextmanager
    def routed(self, paths, endpoints):
        """Traffic split across several paths by endpoints, for the block
        (T21). Default Actions stay Bypass, so anything no endpoint
        matches (ARP) goes straight through. Requires an idle engine and
        leaves it idle: Emulation off, endpoints deleted, then paths (a
        path can't be deleted while an endpoint uses it)."""
        self.open_engine()
        self.require_idle()
        try:
            for spec in paths:
                self.delete_path(spec.name)
                self.create_path(spec)
                self.open_engine()
            for endpoint in endpoints:
                self.create_endpoint(endpoint)
            self.set_emulation(True)
            yield
        finally:
            self.open_engine()
            self.set_emulation(False)
            for endpoint in endpoints:
                self.delete_endpoint(endpoint.label)
            for spec in paths:
                self.delete_path(spec.name)

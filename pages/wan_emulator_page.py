"""The WAN emulator as a page object. The proven T15 helpers in
wan_emulator.py do the work; this adds a generic path builder keyed by the
form's `name` attributes (docs/wan-emulator-reference.md lists every field),
so loss, jitter, outage and the like need no new selectors.

    with WanEmulatorPage(wan_page).impairment_between_ntg_ports("t16-loss", {
        "wan/source-to-destination/loss/method": "random",
        "wan/source-to-destination/loss/random/rate": "1",
    }):
        ...  # run NTG traffic on Ports 3/4
"""
import contextlib

from playwright.sync_api import Page, expect

import wan_emulator
from pages.base_page import BasePage


class WanEmulatorPage(BasePage):
    ENGINE = wan_emulator.NTG_ENGINE          # Engine 2 = emu ports 3/4 = NTG Port 3 <-> 4
    ENGINE_INDEX = wan_emulator.ENGINE_INDEX

    def __init__(self, page: Page):
        super().__init__(page)

    def login(self) -> None:
        wan_emulator.login(self.page)

    def open_engine(self, engine: str = None) -> None:
        wan_emulator.open_engine(self.page, engine or self.ENGINE)

    def set_emulation(self, on: bool) -> None:
        wan_emulator.set_emulation(self.page, on)

    def default_actions(self) -> dict:
        return wan_emulator.default_actions(self.page)

    def set_default_actions(self, labels) -> None:
        wan_emulator.set_default_actions(self.page, labels)

    def delete_path(self, name: str) -> None:
        wan_emulator.delete_path(self.page, name)

    def create_path(self, name: str, fields: dict, wide_open: bool = True) -> None:
        """Create a path from {form field name: value}. Selects take the
        option *value* (e.g. "random", not "Random"). Method selects are
        set before their revealed sub-fields. `wide_open` first lifts both
        access links off their 128 Kbps default."""
        page = self.page
        page.locator("a[href='/path/create']").click()
        page.get_by_placeholder("Enter Path Name...").fill(name)
        values = {}
        if wide_open:
            for link in wan_emulator._ACCESS_LINKS:
                values[f"{link}/bandwidth/metric"] = "Gbps"
                values[f"{link}/bandwidth/rate"] = str(wan_emulator.WIDE_OPEN_GBPS)
        values.update({k: str(v) for k, v in fields.items()})
        # Methods first: they reveal the fields that hold their parameters.
        for key in sorted(values, key=lambda k: not k.endswith("/method")):
            control = page.locator(f"[name='{key}']").first
            if control.evaluate("e => e.tagName") == "SELECT":
                control.select_option(values[key])
            else:
                control.fill(values[key])
                control.press("Tab")
            expect(control).to_have_value(values[key])
        page.get_by_role("button", name="Create Path").click()
        expect(wan_emulator.path_link(page, name)).to_be_visible(timeout=15_000)

    @contextlib.contextmanager
    def impairment_between_ntg_ports(self, name: str, fields: dict):
        """Apply path `name` (built from `fields`) to all NTG Port 3 <-> 4
        traffic for the block, then restore Engine 2 exactly as it was."""
        self.open_engine()
        was_on = wan_emulator.emulation_toggle(self.page).is_checked()
        before = self.default_actions()
        if name in before.values():
            self.set_emulation(False)
            self.set_default_actions("Bypass")
        self.delete_path(name)
        try:
            self.create_path(name, fields)
            self.open_engine()
            self.set_default_actions(name)
            self.set_emulation(True)
            yield
        finally:
            self.open_engine()
            self.set_emulation(False)
            self.set_default_actions(
                {port: "Bypass" if label == name else label for port, label in before.items()}
            )
            self.delete_path(name)
            self.open_engine()
            self.set_emulation(was_on)

    def delay_between_ntg_ports(self, name: str, delay_ms: float):
        return wan_emulator.delay_between_ntg_ports(self.page, name, delay_ms)

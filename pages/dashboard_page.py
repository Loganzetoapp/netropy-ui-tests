import re

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from pages import settings
from pages.base_page import BasePage, port_label, port_number
from pages.errors import PortsBusyError


class DashboardPage(BasePage):
    """The dashboard: Port Status, the Testbeds list (card or table view)
    and the actions on a testbed tile."""

    def __init__(self, page: Page):
        super().__init__(page)
        self.create_button = page.get_by_role("button", name="✚ Create Testbed", exact=True)
        self.testbeds_card = page.locator(".card").filter(has_text="Testbeds")

    # --- navigation ---------------------------------------------------
    def open(self) -> None:
        """From anywhere in the app back to a loaded dashboard. Uses the
        SPA's own "← Dashboard" (a hard reload mid-run has crashed teardown
        before, and goto("/") stays on Settings) and discards unsaved edits.
        Works with a modal left open by a failed step (teardown needs that)."""
        self.close_modals()
        back = self.page.get_by_role("button", name="← Dashboard")
        if back.is_visible():
            back.click()
            discard = self.page.get_by_role("button", name="Discard", exact=True)
            try:
                discard.wait_for(state="visible", timeout=1_500)
                discard.click()
            except PlaywrightTimeoutError:
                pass
        else:
            self.page.goto("/")
        expect(self.page.get_by_text("Port Status")).to_be_visible(timeout=20_000)
        self.wait_loaded()

    def close_modals(self) -> None:
        """Dismiss any open app modal (they are plain .modal-overlay divs
        with no role="dialog") via its Cancel/Close button, else Escape."""
        overlay = self.page.locator(".modal-overlay")
        for _ in range(3):
            if overlay.count() == 0 or not overlay.first.is_visible():
                return
            close = overlay.first.get_by_role("button", name=re.compile(r"^(Cancel|Close|✕|×)$"))
            if close.count():
                close.first.click()
            else:
                self.page.keyboard.press("Escape")
            try:
                expect(overlay).to_have_count(0, timeout=3_000)
            except AssertionError:
                continue

    def wait_loaded(self) -> None:
        """Block until the Testbeds list has loaded ("N saved · M active").
        Port Status renders first, so an instant tile count right after
        landing would see zero cards."""
        expect(
            self.testbeds_card.get_by_text(re.compile(r"^\d+ saved · \d+ active$"))
        ).to_be_visible(timeout=20_000)

    # --- ports --------------------------------------------------------
    def port_row(self, port):
        # Anchored: "Port 3" must not also match a row whose text mentions it.
        return self.page.get_by_role("row", name=re.compile(rf"^{port_label(port)}\b"))

    def first_unreserved_port(self):
        """The lowest-numbered port showing "Unreserved", or None."""
        for n in range(1, 9):
            if self.port_row(n).get_by_text("Unreserved", exact=True).is_visible():
                return n
        return None

    def reserve_port(self, port) -> None:
        row = self.port_row(port)
        row.get_by_role("button", name="Reserve", exact=True).click()
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible()
        expect(row.get_by_role("button", name="Release", exact=True)).to_be_visible()

    def release_port(self, port) -> None:
        """Release a port this test reserved by hand (plain reservation, no
        testbed). Never call this on a port you didn't reserve."""
        row = self.port_row(port)
        row.get_by_role("button", name="Release", exact=True).click()
        expect(row.get_by_text("Unreserved", exact=True)).to_be_visible()
        expect(row.get_by_role("button", name="Reserve", exact=True)).to_be_visible()

    @staticmethod
    def port_holders(ports, own_testbed: str = None) -> dict:
        """{port number: "testbed 'X' (user)"} for each of `ports` held by
        anyone else's testbed. Read from the Controller's port list
        (`mine`, `test-name`, `user`), which is exact where the UI's
        Release button is not (it shows on ports we can't release)."""
        from ntg_api import NtgApi

        api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
        wanted = {port_number(p) for p in ports}
        busy = {}
        for row in api.ports():
            if row["port-id"] not in wanted or not row.get("reserved"):
                continue
            if row.get("mine") or (own_testbed and row.get("test-name") == own_testbed):
                continue
            busy[row["port-id"]] = f"testbed {row.get('test-name')!r} ({row.get('user')})"
        return busy

    def require_ports_free(self, ports, own_testbed: str = None) -> None:
        busy = self.port_holders(ports, own_testbed)
        if busy:
            held = ", ".join(f"Port {n} by {who}" for n, who in sorted(busy.items()))
            raise PortsBusyError(f"Ports in use by someone else: {held}")

    # --- testbeds -----------------------------------------------------
    def testbed_entry(self, name: str):
        """A testbed's card tile, matched on its exact name (so "T10-A"
        never also matches "T10-AB"). The page fixture pins card view."""
        return self.page.locator(".tb-tile").filter(has=self.page.get_by_text(name, exact=True))

    def create_testbed(self, name: str, activatable: bool = True):
        """Create an inactive Traffic Engine draft; returns its tile. With
        `activatable` (the default) the name must fit the 15-char limit
        that activation needs; drafts that are never started may skip it."""
        assert not activatable or len(name) <= settings.MAX_TESTBED_NAME_LEN, (
            f"Testbed name {name!r} is over {settings.MAX_TESTBED_NAME_LEN} chars; "
            "the unit saves it but 502s on activate."
        )
        self.create_button.click()
        self.page.get_by_placeholder("e.g. web-perf-01").fill(name)
        self.page.get_by_role("button", name="Traffic Engine", exact=True).click()
        self.page.get_by_role("button", name="Create draft", exact=True).click()
        tile = self.testbed_entry(name)
        expect(tile).to_have_count(1, timeout=10_000)
        return tile

    def open_draft(self, name: str, ports=(), step: int = None, network_view: str = None):
        """A fresh draft `name` (any old one removed) open in the editor,
        with `ports` enabled and step `step` expanded; returns the editor.
        For hardware-free tests: a draft reserves nothing."""
        from pages.testbed_editor_page import TestbedEditorPage

        self.remove_testbed(name)
        self.create_testbed(name, activatable=False)
        self.open_editor(name)
        editor = TestbedEditorPage(self.page)
        for port in ports:
            editor.set_port_enabled(port, True)
        if step:
            editor.open_step(step)
        if network_view:
            editor.set_network_view(network_view)
        return editor

    def open_editor(self, name: str) -> None:
        self.testbed_entry(name).get_by_role("button", name="Edit").click()
        expect(self.page.get_by_role("heading", name="Ports")).to_be_visible(timeout=15_000)

    def open_stats(self, name: str) -> None:
        self.testbed_entry(name).get_by_role("button", name="Stats").click()
        expect(self.page.get_by_role("heading", name=re.compile(r"^Statistics"))).to_be_visible(
            timeout=30_000
        )

    def tile_button(self, name: str, label: str):
        return self.testbed_entry(name).get_by_role("button", name=label, exact=True)

    def is_running(self, name: str):
        """A locator that is visible exactly while `name` has traffic running."""
        return self.tile_button(name, "Stop")

    def keeps_running(self, name: str, seconds: int) -> None:
        """Assert `name` stays live (Stop visible) for `seconds` more,
        checked every second: catches a run that silently ends early."""
        stop = self.is_running(name)
        for elapsed in range(seconds):
            assert stop.count() == 1 and stop.is_visible(), (
                f"{name}: run ended {elapsed}s into a {seconds}s keep-running check. "
                f"Toasts: {self.toasts()!r}"
            )
            self.page.wait_for_timeout(1_000)  # poll interval

    def start_from_tile(self, name: str, timeout: int = 90_000) -> None:
        from pages.testbed_editor_page import TestbedEditorPage

        TestbedEditorPage(self.page).start(self.tile_button(name, "Start"), timeout)

    def stop_from_tile(self, name: str, timeout: int = 30_000) -> None:
        stop = self.tile_button(name, "Stop")
        expect(stop).to_be_visible(timeout=15_000)
        stop.click()
        expect(stop).to_have_count(0, timeout=timeout)

    def clone_testbed(self, name: str, new_name: str):
        """The tile's "Clone (without ports)" icon -> name -> Clone."""
        self.testbed_entry(name).locator('[data-tip*="Clone" i] button').click()
        field = self.page.locator(".modal-overlay").get_by_role("textbox").first
        field.fill(new_name)
        self.page.get_by_role("button", name="Clone", exact=True).click()
        tile = self.testbed_entry(new_name)
        expect(tile).to_have_count(1, timeout=15_000)
        return tile

    def reports_button(self, name: str):
        """5.0.9: a button labelled with the saved-run count ("1"), tooltip
        "View saved runs on the Stats page"."""
        return self.testbed_entry(name).get_by_role("button", name=re.compile(r"^\d+$"))

    def remove_testbed(self, name: str) -> None:
        """Stop, deactivate (frees its ports) and delete testbed `name` if it
        exists. Only ever touches that one testbed, and only one this
        account can delete (the delete button is disabled otherwise)."""
        self.open()
        tile = self.testbed_entry(name)
        if tile.count() == 0:
            return
        stop = tile.get_by_role("button", name="Stop", exact=True)
        if stop.count():
            stop.click()
            expect(stop).to_have_count(0, timeout=30_000)
        tile.locator('[data-tip="Delete"] button').click()
        # Active testbeds get "Deactivate / Delete" first; deactivate so the
        # ports are released cleanly, then delete the inactive draft.
        deactivate = self.page.get_by_role("button", name="Deactivate", exact=True)
        try:
            deactivate.wait_for(state="visible", timeout=2_000)
        except PlaywrightTimeoutError:
            pass
        else:
            deactivate.click()
            expect(deactivate).to_be_hidden(timeout=30_000)
            tile.locator('[data-tip="Delete"] button').click()
        self.page.get_by_role("button", name="Delete", exact=True).last.click()
        expect(tile).to_have_count(0, timeout=20_000)

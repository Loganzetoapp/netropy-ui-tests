import re

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from pages.base_page import BasePage, port_label, port_number

# NTG 5.0 default "auto" activation: Start on an inactive testbed opens this
# confirm, then Continue runs deactivate-conflicts -> activate -> start. The
# dialog has no role="dialog", so it is found by its title text.
START_POPUP_TITLE = "Testbed is Inactive"

DIRECTIONS = ("bidirectional", "tx only", "rx only")


class TestbedEditorPage(BasePage):
    """The per-testbed config editor: 1 Ports, 2 Network Configuration,
    3 Streams, 4 Traffic and Load Profile, and the bottom bar."""

    __test__ = False  # not a pytest test class, despite the name

    def __init__(self, page: Page):
        super().__init__(page)
        self.start_button = page.get_by_role("button", name="Start", exact=True)
        self.save_button = page.get_by_role("button", name="Save", exact=True)

    # --- steps --------------------------------------------------------
    def step_header(self, number: int):
        return self.page.get_by_role("button", name=re.compile(rf"^{number} ")).first

    def open_step(self, number: int, only: bool = False) -> None:
        """Expand step `number` (headers toggle, so click only when
        collapsed). `only` also collapses the other steps, as Next does,
        so page-wide lookups see just this step."""
        header = self.step_header(number)
        if header.get_attribute("aria-expanded") != "true":
            header.click()
        expect(header).to_have_attribute("aria-expanded", "true")
        if only:
            for other in self.STEP_TITLES:
                if other != number:
                    h = self.step_header(other)
                    if h.get_attribute("aria-expanded") == "true":
                        h.click()
                        expect(h).to_have_attribute("aria-expanded", "false")

    STEP_TITLES = {1: "Ports", 2: "Network Configuration", 3: "Streams", 4: "Traffic and Load Profile"}

    def step_tab(self, number: int):
        """The stepper tab for step `number` in the "Editor steps" tablist.
        Its name is "<mark> <Title> <status>", where the mark is the step
        number, "✓" (complete) or "✗" (invalid), e.g. "✗ Streams 0 streams",
        so match on the title."""
        title = re.escape(self.STEP_TITLES[number])
        return self.page.get_by_role("tablist", name="Editor steps").get_by_role(
            "tab", name=re.compile(rf"^\S+\s+{title}\b")
        )

    # --- 1 Ports ------------------------------------------------------
    def port_row(self, port):
        # Anchored: the Port 4 row's text lists "Port 3" as its peer.
        return self.page.get_by_role("row", name=re.compile(rf"^{re.escape(port_label(port))}\b"))

    def set_port_enabled(self, port, enabled: bool = True) -> None:
        use = self.port_row(port).get_by_role("checkbox").first
        if use.is_checked() != enabled:
            # The checkbox is visually replaced by a toggle track; click its wrapper.
            use.locator("xpath=..").click()
        expect(use).to_be_checked(checked=enabled)

    def set_line_rate(self, port, rate, unit: str = "Gbps") -> None:
        row = self.port_row(port)
        row.get_by_role("combobox").last.select_option(unit)
        field = row.get_by_role("spinbutton")
        field.fill(str(rate))
        field.press("Tab")
        expect(field).to_have_value(str(rate))

    def set_direction(self, port, direction: str) -> None:
        """bidirectional / tx only / rx only (tx_only and rx_only accepted)."""
        label = direction.replace("_", " ")
        assert label in DIRECTIONS, f"direction {direction!r} not one of {DIRECTIONS}"
        select = self.port_row(port).get_by_role("combobox").filter(
            has=self.page.get_by_role("option", name="bidirectional")
        )
        select.select_option(label=label)
        expect(select.locator("option:checked")).to_have_text(label)

    def set_peer(self, port, peer) -> None:
        select = self.port_row(port).get_by_role("combobox").filter(
            has=self.page.get_by_role("option", name="— none —")
        )
        label = port_label(peer) if peer else "— none —"
        select.select_option(label=label)
        expect(select.locator("option:checked")).to_have_text(label)

    def enable_ports(self, ports, rate=None, unit: str = "Gbps") -> None:
        """Turn on each port (two ports auto-peer) and optionally set every
        one's line rate."""
        self.open_step(1)
        for port in ports:
            self.set_port_enabled(port, True)
            if rate is not None:
                self.set_line_rate(port, rate, unit)

    # --- 2 Network Configuration (5.0's default Table view) ------------
    def set_network_view(self, view: str) -> None:
        """Step 2's Table / Cards view toggle (5.0 opens in Table)."""
        self.open_step(2)
        tab = self.page.get_by_role("tab", name=re.compile(rf"{view}$"))
        if tab.get_attribute("aria-selected") != "true":
            tab.click()
        expect(tab).to_have_attribute("aria-selected", "true")
        if view == "Cards":
            expect(self.network_cards().first).to_be_visible(timeout=10_000)

    def network_cards(self):
        """Per-port cards in step 2's Cards view."""
        return self.page.locator(".ne-pcard")

    def network_row(self, port):
        return self.page.get_by_role("row", name=re.compile(rf"^{port_number(port)}\s"))

    def set_port_address(self, port, ip: str, cidr, dst_ip: str = None, gateway_ip: str = None) -> None:
        """Source IP + /cidr (25–32 only on 5.0.9) and optionally the
        destination IP and a gateway next hop for one port."""
        self.open_step(2)
        row = self.network_row(port)
        src = row.get_by_role("textbox", name="10.1.0.10")
        src.fill(ip)
        src.press("Tab")
        # Select by value ("25"); the labels are "/25".
        row.get_by_role("combobox").first.select_option(str(cidr).lstrip("/"))
        expect(src).to_have_value(ip)
        if dst_ip:
            dst = row.get_by_role("textbox", name="auto").first
            dst.fill(dst_ip)
            dst.press("Tab")
            expect(dst).to_have_value(dst_ip)
        if gateway_ip:
            next_hop = row.get_by_role("combobox").filter(
                has=self.page.get_by_role("option", name="Gateway")
            )
            next_hop.select_option(label="Gateway")
            # The gateway field's only accessible name is its placeholder.
            gw = row.get_by_role("textbox", name="none")
            gw.fill(gateway_ip)
            gw.press("Tab")
            expect(gw).to_have_value(gateway_ip)

    def set_addressing(self, ports, ips, cidr) -> None:
        """A two-port pair: each port gets its source IP on a /cidr and
        points its destination at its peer's source IP."""
        for port, ip, peer_ip in zip(ports, ips, reversed(ips)):
            self.set_port_address(port, ip, cidr)
        for port, ip, peer_ip in zip(ports, ips, reversed(ips)):
            self.set_port_address(port, ip, cidr, dst_ip=peer_ip)

    # --- 3 Streams ----------------------------------------------------
    def stream_rows(self):
        # The per-row delete icon has no accessible name, only a data-tip.
        return self.page.locator("tr").filter(has=self.page.locator('span[data-tip="Delete stream"]'))

    def add_stream(self, protocol: str, quantity: int = 1, name: str = None) -> None:
        """Add `quantity` streams of `protocol` (the Add Stream modal's list
        button, e.g. "UDP", "TCP", "ICMP", "DNS", "HTTP", "UDP (IPv6)")."""
        self.open_step(3)
        rows = self.stream_rows()
        before = rows.count()
        self.page.get_by_role("button", name="✚ Add Stream").click()
        # The modal is a plain .modal-overlay div (no role="dialog"). Its
        # Name and Quantity fields have no labels (5.0.9): Name is the
        # textbox under the "Name (prefix…)" caption (the first textbox is
        # the protocol search), Quantity the only spinbutton.
        modal = self.page.locator(".modal-overlay")
        modal.get_by_role("button", name=re.compile(rf"^{re.escape(protocol)}( WIP)?$")).first.click()
        if name:
            modal.get_by_text("Name (prefix when adding several)", exact=True).locator(
                "xpath=.."
            ).get_by_role("textbox").fill(name)
        if quantity != 1:
            modal.get_by_role("spinbutton").fill(str(quantity))
        # "Add stream", or "Add 2 streams" when quantity > 1.
        modal.get_by_role("button", name=re.compile(r"^Add( \d+)? streams?$")).click()
        expect(rows).to_have_count(before + quantity)

    def set_all_frame_sizes(self, size: int) -> None:
        """The "Frame size — apply to all" control."""
        self.open_step(3)
        apply = self.page.get_by_role("button", name="Apply to all", exact=True)
        # The size field sits beside the button, in the same container.
        apply.locator("xpath=..").get_by_role("spinbutton").fill(str(size))
        apply.click()
        rows = self.stream_rows()
        for i in range(rows.count()):
            expect(rows.nth(i).get_by_role("spinbutton")).to_have_value(str(size))

    def set_stream_frame_size(self, index: int, size: int) -> None:
        """Frame size of the `index`-th stream row (0-based, in add order)."""
        self.open_step(3)
        field = self.stream_rows().nth(index).get_by_role("spinbutton")
        field.fill(str(size))
        field.press("Tab")
        expect(field).to_have_value(str(size))

    # --- 4 Traffic and Load Profile -------------------------------------
    def open_load_profile(self) -> None:
        """Step 4, with its traffic profile rendered (the USED pill)."""
        self.open_step(4)
        expect(self.page.locator(".pill", has_text="used")).to_be_visible(timeout=10_000)

    def load_profile_checkbox(self):
        """The Load profile toggle: an unlabelled checkbox beside the
        "Load profile" title (5.0.9: "Disabled | Runs until Manual Stop" /
        "Ramp enabled")."""
        return (
            self.page.locator("div", has=self.page.get_by_text("Load profile", exact=True))
            .filter(has=self.page.get_by_role("checkbox"))
            .last.get_by_role("checkbox")
            .first
        )

    def ramp_field(self, label: str):
        """"Ramp up" / "Hold time" / "Ramp down" seconds input."""
        return self.page.locator(".fg", has_text=label).locator('input[type="number"]').first

    def total_run_time(self):
        return self.page.get_by_text(re.compile(r"Total run time"))

    def set_load_profile_enabled(self, enabled: bool = True) -> None:
        self.open_step(4)
        box = self.load_profile_checkbox()
        if box.is_checked() != enabled:
            box.locator("xpath=..").click()
        expect(box).to_be_checked(checked=enabled)

    def set_ramp(self, up: int, hold: int, down: int) -> None:
        """Enable the load ramp and set its phases (seconds), so the run
        ends on its own after up + hold + down."""
        self.set_load_profile_enabled(True)
        for label, secs in (("Ramp up", up), ("Hold time", hold), ("Ramp down", down)):
            field = self.ramp_field(label)
            field.fill(str(secs))
            field.press("Tab")
        expect(self.total_run_time()).to_contain_text(
            f"= {up + hold + down}s"
        )

    def set_duration(self, seconds: int) -> None:
        """Run at full rate for `seconds`, then stop (a 0/N/0 ramp)."""
        self.set_ramp(0, seconds, 0)

    # --- bottom bar ---------------------------------------------------
    def save(self) -> None:
        """Save, and wait until the Controller has accepted the change.

        Save is enabled exactly while there are unsaved changes, and a click
        sends PUT /tests/<name>; its response is the end signal. Not the
        "unsaved" badge: it clears when the PUT is *sent*, and on 5.0.10 its
        text is "UNSAVED" only through CSS, so matching that text never
        waited at all (probes 2026-10-16). Even after the 200 the Controller
        can take ~0.1 s more to return the new config from GET /tests/<name>,
        so a test reading it straight back should poll."""
        try:
            expect(self.save_button).to_be_enabled(timeout=2_000)
        except AssertionError:
            return  # nothing to save: the click would send no request
        with self.page.expect_response(_is_testbed_save, timeout=15_000) as saved:
            self.save_button.click()
        response = saved.value
        assert response.ok, f"Save refused: HTTP {response.status} {response.text()[:300]}"
        expect(self.save_button).to_be_disabled(timeout=15_000)

    def start(self, start_button=None, timeout: int = 90_000) -> None:
        """Click Start, confirm "Testbed is Inactive", and wait for traffic to
        actually run (a Stop button appears). `start_button` defaults to the
        editor bar's Start; pass a tile's Start to start from the dashboard.
        A rejected start shows only as a toast, so the failure quotes it."""
        (start_button or self.start_button).click()
        title = self.page.get_by_text(START_POPUP_TITLE, exact=True)
        # Already active + synced testbeds skip the popup and start directly.
        try:
            title.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError:
            pass
        else:
            self.page.get_by_role("button", name="Continue").click()
            expect(title).to_be_hidden()
        stop = self.page.get_by_role("button", name="Stop", exact=True).first
        try:
            expect(stop).to_be_visible(timeout=timeout)
        except AssertionError as exc:
            raise AssertionError(
                f"Traffic never started after Start → Continue. On-screen toasts: {self.toasts()!r}"
            ) from exc


def _is_testbed_save(response) -> bool:
    """The editor's Save: PUT /ctrl/v1/tests/<name> (or the unit-scoped form)."""
    return response.request.method == "PUT" and bool(
        re.search(r"/ctrl/v1/(units/[^/]+/)?tests/[^/?]+$", response.url)
    )

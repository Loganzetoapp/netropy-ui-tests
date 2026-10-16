import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from pages.errors import SystemBadStateError

# Shown on Statistics when the testbed is active but nothing is running.
# 5.0 can accept Start, look live for a while, then fall back to this with
# no saved run and no error (seen 4/4 for NTP, 2026-10-01).
_ARMED_IDLE = re.compile(r"Ports are armed and idle", re.I)
_LATENCY_MS = re.compile(r"([\d,]+(?:\.\d+)?)\s*ms")


class RunPage(BasePage):
    """Statistics — <testbed>: live view and the Test Reports table."""

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name=re.compile(r"^Statistics"))

    def run_row(self, run_number: int):
        # Row text runs straight into the badge ("#1LATEST…"), so no \b here.
        return self.page.get_by_role("row").filter(has_text=re.compile(rf"^\s*#{run_number}(?!\d)"))

    def wait_for_run_to_finish(self, run_number: int = 1, timeout: int = 5 * 60_000):
        """After start() from the editor (which lands on Statistics): block
        until run #`run_number` is saved to Test Reports, i.e. the run ended,
        and return that row. Saved rows are the reliable end signal; the
        Stop button is not (the hand-off briefly shows neither Start nor Stop).
        Ending up "armed and idle" with no saved run is a lost run: a
        SystemBadStateError."""
        expect(self.heading).to_be_visible(timeout=30_000)
        row = self.run_row(run_number)
        idle = self.page.get_by_text(_ARMED_IDLE)
        idle_ms, waited = 0, 0
        while row.count() != 1:
            if waited >= timeout:
                raise AssertionError(
                    f"Run #{run_number} was not saved within {timeout // 1000}s. {self.state()}"
                )
            idle_ms = idle_ms + 1_000 if idle.count() else 0
            if idle_ms >= 15_000:
                raise SystemBadStateError(
                    f"Run #{run_number} ended but was never saved (stats lost). {self.state()}"
                )
            self.page.wait_for_timeout(1_000)  # poll interval, not a settle wait
            waited += 1_000
        return row

    @staticmethod
    def verdict(row) -> str:
        """The RESULT cell of a Test Reports row, lowercased ("pass"/"fail")."""
        cell = row.get_by_text(re.compile(r"^(pass|fail)$", re.I))
        expect(cell).to_be_visible(timeout=30_000)
        return cell.inner_text().strip().lower()

    def assert_passed(self, row) -> None:
        """The whole row goes in the message, so a FAIL says why."""
        verdict = self.verdict(row)
        assert verdict == "pass", f"run verdict {verdict!r}; saved run row: {row.inner_text()!r}"

    def verdict_once(self, row, expected: str, timeout: int = 15_000) -> str:
        """The row's verdict once it reads `expected`, or whatever it still
        reads after `timeout`. Re-judging a saved run (new pass criteria)
        updates the cell asynchronously; this lets the caller record the
        verdict instead of failing on the first stale read."""
        cell = row.get_by_text(re.compile(rf"^{re.escape(expected)}$", re.I))
        try:
            expect(cell).to_be_visible(timeout=timeout)
        except AssertionError:
            pass
        return self.verdict(row)

    # --- pass criteria ------------------------------------------------
    # The result cell's ⚙ button ("Edit pass criteria", a tooltip only)
    # opens a popover per saved run. Its three rules are number inputs
    # whose <label> isn't tied to them, so they have no accessible names
    # (a11y; data-testid wanted): each is found inside its rule's block.
    _CRITERIA_RULES = {"max_loss_pct": "Max loss", "max_latency_ms": "Max latency",
                       "min_rx_pct": "Min Rx"}

    def criteria_popover(self, run_number: int):
        title = self.page.get_by_text(re.compile(rf"^Pass criteria — Run #{run_number}$"))
        return title.locator("xpath=ancestor::div[.//button[normalize-space()='Save']][1]")

    def set_pass_criteria(self, run_number: int, max_loss_pct=None, max_latency_ms=None,
                          min_rx_pct=None) -> None:
        """Set saved run #`run_number`'s pass criteria and save. A rule
        given as None is turned off (empty field); 0 is a real threshold
        ("0 = require zero loss"). The NTG re-judges the run against them."""
        values = {"max_loss_pct": max_loss_pct, "max_latency_ms": max_latency_ms,
                  "min_rx_pct": min_rx_pct}
        self.run_row(run_number).get_by_role("button", name="⚙").click()
        popover = self.criteria_popover(run_number)
        expect(popover).to_be_visible()
        for key, label in self._CRITERIA_RULES.items():
            field = popover.locator(".fg").filter(has_text=label).get_by_role("spinbutton")
            text = "" if values[key] is None else f"{values[key]:g}"
            field.fill(text)
            expect(field).to_have_value(text)
        popover.get_by_role("button", name="Save", exact=True).click()
        expect(popover).to_be_hidden(timeout=15_000)

    def last_run_avg_latency_ms(self) -> float:
        """The "Avg Latency" card of the latest saved run (e.g. "0.224 ms"),
        behind the "Last run #N" button. Call on a Statistics page opened
        after the run was saved (DashboardPage.open_stats)."""
        self.page.get_by_role("button", name=re.compile(r"^Last run #")).click()
        card = self.page.get_by_role("button", name="Avg Latency: open graph")
        expect(card).to_contain_text(_LATENCY_MS, timeout=20_000)
        return float(_LATENCY_MS.search(card.inner_text()).group(1).replace(",", ""))

    def rows(self):
        return self.page.get_by_role("row").filter(has_text=re.compile(r"^\s*#\d+"))

    def export(self, row, fmt: str):
        """Click a run row's export button (PDF / XLSX / CSV / JSON / FULL /
        ZIP) and return the Download."""
        with self.page.expect_download(timeout=30_000) as download:
            row.get_by_role("button", name=fmt, exact=True).click()
        return download.value

    def delete_run(self, row) -> None:
        row.get_by_role("button", name="Delete run").click()
        confirm = self.page.get_by_role("button", name="Delete", exact=True)
        try:
            confirm.last.wait_for(state="visible", timeout=2_000)
            confirm.last.click()
        except Exception:
            pass
        expect(row).to_have_count(0, timeout=15_000)

    def state(self) -> str:
        header = self.page.locator("h1, h2").first.locator("xpath=..").inner_text()[:300]
        status = self.page.get_by_text(
            re.compile(r"^LIVE ·|Ready to start|armed", re.I)
        ).all_inner_texts()
        return f"Header: {header!r}; status text: {status!r}; toasts: {self.toasts()!r}"

import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from pages.errors import SystemBadStateError

# Shown on Statistics when the testbed is active but nothing is running.
# 5.0 can accept Start, look live for a while, then fall back to this with
# no saved run and no error (seen 4/4 for NTP, 2026-10-01).
_ARMED_IDLE = re.compile(r"Ports are armed and idle", re.I)


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

    def state(self) -> str:
        header = self.page.locator("h1, h2").first.locator("xpath=..").inner_text()[:300]
        status = self.page.get_by_text(
            re.compile(r"^LIVE ·|Ready to start|armed", re.I)
        ).all_inner_texts()
        return f"Header: {header!r}; status text: {status!r}; toasts: {self.toasts()!r}"

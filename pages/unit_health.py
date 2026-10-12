"""Is the unit itself healthy? Crash detection for "the test never
started": the UI top bar plus a read-only look at the Controller (health,
the testbed's datapath state). Never reads live /stats (that can crash the
Controller on a stopped test; see ntg_api.py)."""
from playwright.sync_api import Page

from pages import settings
from pages.base_page import BasePage
from pages.dashboard_page import DashboardPage
from pages.errors import SystemBadStateError

# Top-bar indicators (polled every 5 s from the Controller's health check).
_UNHEALTHY_TOPBAR = ("offline", "controller offline", "RECOVERY")


class UnitHealth(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.dashboard = DashboardPage(page)

    def ui_problems(self) -> list:
        """Back on the dashboard, after one full health poll: anything
        that says the unit isn't healthy."""
        self.dashboard.open()
        self.page.wait_for_timeout(6_000)  # let at least one 5 s health poll land
        problems = [
            f"top bar shows {text!r}"
            for text in _UNHEALTHY_TOPBAR
            if self.page.get_by_text(text, exact=True).count()
        ]
        if self.page.get_by_text("online", exact=True).count() == 0:
            problems.append("top bar never shows 'online'")
        if self.dashboard.testbeds_card.get_by_text("disconnected", exact=True).count():
            problems.append("a testbed is in the 'disconnected' state")
        return problems

    @staticmethod
    def api_snapshot(testbed: str = None) -> dict:
        """Controller health and, for `testbed`, its datapath state and
        latest saved run. Errors are captured, not raised: an unreachable
        Controller is itself the finding."""
        from ntg_api import NtgApi

        api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
        snap = {}
        try:
            snap["health"] = api.health()
        except Exception as exc:
            snap["health"] = f"unreachable: {exc}"
        if testbed:
            try:
                snap["datapath"] = api.datapath_state(testbed)
                latest = api.latest_run(testbed)
                snap["latest_run"] = latest and {
                    k: latest.get(k) for k in ("number", "verdict", "status", "end-reason")
                }
            except Exception as exc:
                snap["testbed"] = f"status unavailable: {exc}"
        return snap

    def assert_healthy(self, context: str = "", testbed: str = None) -> None:
        """Raise SystemBadStateError (a SYSTEM failure, not a test failure)
        when the UI or the Controller says the unit is unhealthy."""
        problems = self.ui_problems()
        snap = self.api_snapshot(testbed)
        health = snap.get("health")
        if not isinstance(health, dict) or health.get("status") != "ok" or health.get("recovery"):
            problems.append(f"controller health: {health!r}")
        if snap.get("datapath") == "ERROR":
            problems.append(f"testbed {testbed!r} datapath is ERROR")
        if problems:
            where = f" ({context})" if context else ""
            raise SystemBadStateError(f"Unit unhealthy{where}: " + "; ".join(problems))

    def diagnose_failed_start(self, testbed: str, error: BaseException) -> None:
        """Start didn't produce running traffic. If the unit is unhealthy,
        raise a system failure explaining why. Otherwise re-raise the
        original error with the Controller's view of the testbed attached."""
        self.assert_healthy(context=f"start of {testbed!r} failed: {error}", testbed=testbed)
        raise AssertionError(
            f"{error}\nUnit healthy; Controller view: {self.api_snapshot(testbed)!r}"
        ) from error

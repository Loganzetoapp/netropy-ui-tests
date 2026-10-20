from playwright.sync_api import Page, expect

from pages import settings
from pages.base_page import BasePage


class LoginPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.username_input = page.get_by_placeholder("username")
        self.password_input = page.get_by_placeholder("password")
        self.sign_in_button = page.get_by_role("button", name="Sign in")

    def open(self, url: str = None) -> None:
        self.page.goto(url or settings.NTG_URL)

    def submit(self, username: str, password: str) -> None:
        """Fill and send the sign-in form without asserting where it lands
        (T1 uses this for the wrong-password case)."""
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.sign_in_button.click()

    def login(self, username: str = None, password: str = None, url: str = None) -> None:
        """Sign in with .env credentials unless others are given, and wait
        for the dashboard. Returns at once if the session is still valid."""
        self.open(url)
        dashboard = self.page.get_by_text("Port Status")
        try:
            expect(dashboard.or_(self.username_input)).to_be_visible(timeout=15_000)
        except AssertionError:
            pass
        if dashboard.is_visible():
            return
        self.submit(username or settings.NTG_USER, password or settings.NTG_PASS)
        expect(dashboard).to_be_visible()

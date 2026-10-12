from playwright.sync_api import Page


def port_label(port) -> str:
    """3 or "3" or "Port 3" -> "Port 3"."""
    text = str(port)
    return text if text.startswith("Port ") else f"Port {text}"


def port_number(port) -> int:
    """3 or "3" or "Port 3" -> 3."""
    return int(str(port).replace("Port ", ""))


class BasePage:
    def __init__(self, page: Page):
        self.page = page

    def toasts(self) -> list:
        """Text of every toast on screen. The app reports most errors only
        as toasts, so failures quote these."""
        return self.page.locator(".toast").all_inner_texts()

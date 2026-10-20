import os
import re

from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright, expect

load_dotenv()
BASE_URL = os.environ["NETROPY_URL"]
USERNAME = os.environ["NETROPY_USER"]
PASSWORD = os.environ["NETROPY_PASS"]


BUFFER_MS = 400


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    def buffer():
        page.wait_for_timeout(BUFFER_MS)

    page.goto(BASE_URL)
    page.get_by_role("textbox", name="username").click()
    page.get_by_role("textbox", name="username").fill(USERNAME)
    page.get_by_role("textbox", name="username").press("Tab")
    page.get_by_role("textbox", name="password").fill("")
    page.get_by_role("textbox", name="password").click()
    page.get_by_role("textbox", name="password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    buffer()
    # Fixed from codegen's raw Reserve.nth(1) x2 (which resolves against
    # *whatever* ports currently show "Reserve" on the dashboard, and shifts
    # after the first click removes a match) to explicit Port 1 / Port 2.
    page.get_by_role("row", name=re.compile(r"^Port 1\b")).get_by_role("button", name="Reserve").click()
    buffer()
    page.get_by_role("row", name=re.compile(r"^Port 2\b")).get_by_role("button", name="Reserve").click()
    buffer()
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    buffer()
    page.get_by_role("textbox", name="e.g. web-perf-").click()
    page.get_by_role("textbox", name="e.g. web-perf-").fill("Playwright_test")
    buffer()
    page.get_by_role("button", name="Create draft").click()
    buffer()
    page.get_by_role("button", name="Edit").nth(5).click()
    buffer()
    # Codegen recorded a redundant .check() on each toggle's hidden native
    # checkbox alongside the visible-switch click — Playwright won't
    # interact with it directly since the custom .toggle styling hides it.
    # The switch click alone is what the real spec files do too. Each
    # toggle needs a settle buffer before the next locator's actionability
    # wait, or the wizard's "N port(s) selected" validation can lag behind
    # and the next step's button stays disabled.
    page.locator(".track").first.click()
    buffer()
    page.locator("tr:nth-child(2) > td > div > .toggle > .track").click()
    buffer()
    page.get_by_role("button", name="2 Network Configuration per-").click()
    buffer()
    page.get_by_role("textbox", name="10.1.0.10").first.click()
    page.get_by_role("textbox", name="10.1.0.10").first.fill("10.0.0.2")
    buffer()
    page.get_by_role("textbox", name="auto").first.click()
    page.get_by_role("textbox", name="auto").first.fill("20.0.0.2")
    buffer()
    page.get_by_role("textbox", name="auto").nth(2).click()
    page.get_by_role("textbox", name="auto").nth(2).fill("10.0.0.2")
    buffer()
    page.get_by_role("textbox", name="10.1.0.10").nth(1).click()
    page.get_by_role("textbox", name="10.1.0.10").nth(1).fill("20.0.0.2")
    buffer()
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    buffer()
    page.get_by_role("button", name="✚ Add Stream").click()
    buffer()
    page.get_by_role("button", name="Add stream", exact=True).click()
    buffer()
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    buffer()
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    buffer()
    page.locator("div:nth-child(2) > .fc > input").fill("50")
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    buffer()
    page.get_by_role("button", name="Apply", exact=True).click()

    # Apply saves + activates on the unit; give it real room (this box's
    # activation is known to legitimately take up to ~75s) before Start.
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    buffer()

    # Recorded as a click on the header logo — leaving as-is, this is what
    # actually happened in the manual recording.
    page.get_by_text("Netropy Traffic Generator", exact=True).click()
    buffer()

    page.get_by_role("button", name="Release").first.click()
    buffer()
    page.get_by_role("button", name="Deactivate & release").click()
    buffer()
    page.get_by_role("button", name="Reserve").nth(2).click()
    buffer()
    page.get_by_role("cell", name="Release Release the").locator("button").click()
    buffer()

    tile = page.locator(".tb-tile").filter(has_text="Playwright_test")
    if tile.count() > 0:
        # Delete icon is the 3rd button in the tile — same convention as
        # the real spec files, instead of codegen's absolute-position
        # div chain, which breaks the moment the dashboard's tile order
        # or internal layout shifts.
        tile.locator("button").nth(2).click()
        buffer()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(tile).to_have_count(0, timeout=10000)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)

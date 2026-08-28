"""T4 — Importing a malformed/truncated file: clear error, no broken card.

Uploading invalid JSON to the Testbeds "Import" file input surfaces a
dismissible toast reading "<filename>: not valid JSON" (top-right,
auto-expiring) and leaves the dashboard's testbed list untouched — no
partial/broken card is created.
"""
import pytest
from playwright.sync_api import Page, expect


def _testbeds_import_input(page: Page):
    return page.locator(".card-hdr").filter(has_text="Testbeds").locator('input[type="file"]')


def _saved_count(page: Page) -> int:
    text = page.locator(".card").filter(has_text="Testbeds").get_by_text(
        "saved", exact=False
    ).inner_text()
    return int(text.split("saved")[0].strip())


@pytest.mark.hardware_free
def test_t4_import_malformed_json_shows_error_no_broken_card(dashboard: Page, tmp_path):
    page = dashboard
    before = _saved_count(page)

    bad_file = tmp_path / "bad_import.json"
    bad_file.write_text("{ this is not valid json ][")

    _testbeds_import_input(page).set_input_files(str(bad_file))

    expect(page.get_by_text(f"{bad_file.name}: not valid JSON")).to_be_visible(timeout=10000)
    assert _saved_count(page) == before

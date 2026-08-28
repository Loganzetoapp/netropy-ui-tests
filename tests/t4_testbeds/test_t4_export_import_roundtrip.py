"""T4 — Export a testbed config, delete it, import it back, compare.

Selector notes from exploration:
- Export (the download icon, data-tip "Export config JSON") opens a
  confirm dialog first — "Export '<name>' — This configuration is
  incomplete and not active on the unit — the exported JSON is the saved
  draft as it stands." with Cancel / "Export anyway" — even for a
  perfectly valid empty draft. There is no way to skip this dialog.
- Import lives in the Testbeds section header as a hidden
  `<input type="file" accept=".json,application/json">`, exposed via a
  visible "Import" button with tooltip "Import testbed JSON". Uploading
  directly to the hidden input (`set_input_files`) works and avoids
  needing to interact with the OS file picker.
- Exported filename is `<testbed-name>.json`; the JSON body is
  `{"name", "feature", "port", "stream"}` — no UID, no run history, no
  license/module metadata. Re-importing gets a fresh UID from the
  server, which is expected (see test_t4_duplicate_testbed.py — the app
  always mints a new UID on creation, whether via Create, Clone, or
  Import).
"""
import json

import pytest
from playwright.sync_api import Page, expect

NAME = "T4-ExportImport-DeleteMe"


def _tile(page: Page, name: str = NAME):
    return page.locator(".tb-tile").filter(has_text=name)


def _testbeds_import_input(page: Page):
    return page.locator(".card-hdr").filter(has_text="Testbeds").locator('input[type="file"]')


def _delete_if_present(page: Page, name: str = NAME):
    tile = _tile(page, name)
    if tile.count() > 0:
        tile.locator('[data-tip="Delete"] button').click()
        page.get_by_role("button", name="Delete", exact=True).click()
        expect(_tile(page, name)).to_have_count(0, timeout=10000)


@pytest.fixture
def clean_up(dashboard: Page):
    _delete_if_present(dashboard)
    yield
    _delete_if_present(dashboard)


@pytest.mark.hardware_free
def test_t4_export_then_import_recreates_equivalent_testbed(dashboard: Page, clean_up, tmp_path):
    page = dashboard

    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    page.get_by_placeholder("e.g. web-perf-01").fill(NAME)
    page.get_by_role("button", name="Traffic Engine", exact=True).click()
    page.get_by_role("button", name="Create draft", exact=True).click()
    expect(_tile(page)).to_have_count(1, timeout=10000)

    tile = _tile(page)
    tile.locator('[data-tip="Export config JSON"] button').click()
    expect(page.get_by_role("button", name="Export anyway", exact=True)).to_be_visible(
        timeout=10000
    )
    with page.expect_download(timeout=10000) as download_info:
        page.get_by_role("button", name="Export anyway", exact=True).click()
    download = download_info.value
    assert download.suggested_filename == f"{NAME}.json"

    export_path = tmp_path / download.suggested_filename
    download.save_as(str(export_path))
    exported = export_path.read_text()

    _delete_if_present(page)

    _testbeds_import_input(page).set_input_files(str(export_path))
    expect(_tile(page)).to_have_count(1, timeout=10000)

    # Round-trip: export the re-imported testbed and compare config bodies
    # (name/feature/port/stream) — not the UID, which is always freshly
    # minted server-side on creation.
    tile = _tile(page)
    tile.locator('[data-tip="Export config JSON"] button').click()
    expect(page.get_by_role("button", name="Export anyway", exact=True)).to_be_visible(
        timeout=10000
    )
    with page.expect_download(timeout=10000) as second_download_info:
        page.get_by_role("button", name="Export anyway", exact=True).click()
    reexported = second_download_info.value.path()

    with open(reexported) as f:
        reexported_data = json.load(f)
    original_data = json.loads(exported)
    assert reexported_data == original_data

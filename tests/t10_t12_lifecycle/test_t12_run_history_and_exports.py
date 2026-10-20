"""T12 — Run history table, export formats, delete a run, Reports badge.

One real run, reused for every T12 assertion rather than paying for
several activations. Confirmed by exploration:
- The run history row: `#1`/`latest` · Started At · Duration · Total
  Test Time · Avg Tx · Avg Rx · Loss % · Result (`pass`, lowercase DOM
  text, styled uppercase — same trap as elsewhere) · a `title` on the
  Result cell reading "loss-based default (no pass criteria set)" —
  still true, matches the open PASS-threshold question in project
  memory. Export buttons scope by their `title` attribute: "Download
  PDF report" / "Download Excel workbook (all sheets)" / "Download CSV"
  / "Download report JSON" / "Download all formats (PDF, XLSX, CSV,
  JSON) as a zip".
- The dashboard tile only shows a "Reports: N" badge once the testbed
  is fully deactivated (ports released) — while ACTIVE it shows a
  "Stats" button instead, even with saved runs. So the Reports-badge
  checks happen after releasing ports, reusing the same testbed.
- Delete run has `aria-label="Delete run"` — no confirm dialog observed
  for a single run's icon delete (unlike testbed/profile delete).

REWRITTEN 2026-10-11 on the shared pages/ library (NTG 5.0.9): the 4.0
click sequence described above (manual Reserve, "Available", Apply,
positional selectors) is gone; the scenario and its assertions are kept.
Runs are recorded on the summary sheet (traffic_engine fixture).
"""
import json

import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec

NAME = "T12-RunHistory"
SPEC = TestbedSpec(ports={1: PortSpec(rate=1), 2: PortSpec(rate=1)},
                   streams=[StreamSpec("ICMP")], ramp=(5, 10, 5))
EXPORTS = {"PDF": ".pdf", "XLSX": ".xlsx", "CSV": ".csv", "JSON": ".json", "ZIP": ".zip", "FULL": None}


@pytest.mark.stateful
def test_t12_run_history_exports_delete_and_reports_badge(dashboard: Page, traffic_engine, tmp_path):
    board, runs = traffic_engine.dashboard, traffic_engine.runs
    result = traffic_engine.run(NAME, SPEC)
    result.assert_passed()

    # --- Run history row ---
    row = runs.run_row(1)
    expect(row).to_contain_text("%")
    expect(row).to_contain_text("bps")

    # --- Exports: every format downloads a non-empty file ---
    for fmt, suffix in EXPORTS.items():
        download = runs.export(row, fmt)
        path = tmp_path / download.suggested_filename
        download.save_as(str(path))
        assert path.stat().st_size > 0, f"{fmt} export is empty"
        if suffix:
            assert path.suffix == suffix, f"{fmt} export saved as {path.name}"
        if fmt == "JSON":
            assert json.loads(path.read_text()), "JSON report has no content"

    # --- Reports count on the tile ---
    board.open()
    expect(board.reports_button(NAME)).to_have_text("1")

    # --- Delete the run ---
    board.reports_button(NAME).click()
    runs.delete_run(runs.run_row(1))
    expect(runs.rows()).to_have_count(0)
    board.open()
    expect(board.reports_button(NAME)).not_to_have_text("1")

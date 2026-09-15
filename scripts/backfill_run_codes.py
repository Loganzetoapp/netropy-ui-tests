"""One-off migration: assign a `run_code` (`RUN-<n>`) to every existing
`results/history/*.json` file that doesn't already have one, in
chronological order by each file's own `run_id` field (the
`YYYYmmddTHHMMSSZ`-format timestamp id `scripts/collect_run.py` already
writes into every history file).

Idempotent — safe to re-run any number of times: files that already carry
a `run_code` are skipped, and codes are minted through
`scripts.collect_run._next_run_code`, the exact same counter
(`results/history/.run_seq`) new runs mint from going forward — so the
sequence just continues from wherever it was left (or starts at 0 if the
counter file doesn't exist yet). Re-running this after new runs have
already been collected normally is safe too: it only ever touches files
missing `run_code`.

    python scripts/backfill_run_codes.py [--history-dir PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from scripts.collect_run import DEFAULT_HISTORY_DIR, RUN_SEQ_FILENAME, _next_run_code

ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # same defensive skip as persistence._load_history / build_report.py


def _pending_entries(history_dir: Path) -> list[tuple[Path, dict]]:
    """Every history file missing run_code, sorted oldest-first by its own
    run_id field (falling back to filename for a rare same-run_id tie,
    e.g. collect_run.py's same-second collision-suffixed files)."""
    entries = []
    for path in sorted(history_dir.glob("*.json")):
        if path.name == RUN_SEQ_FILENAME:
            continue
        data = _load(path)
        if data is None or "run_code" in data:
            continue
        entries.append((path, data))
    entries.sort(key=lambda pd: (pd[1].get("run_id") or "", pd[0].name))
    return entries


def backfill(history_dir: Path = DEFAULT_HISTORY_DIR, dry_run: bool = False) -> list[str]:
    """Assign run codes to every pending file, oldest first. Returns the
    names of the files updated (or, in dry-run mode, that would be)."""
    touched = []
    for path, data in _pending_entries(history_dir):
        if dry_run:
            print(f"backfill_run_codes: would assign a code to {path.name}")
            touched.append(path.name)
            continue
        run_code = _next_run_code(history_dir)
        data["run_code"] = run_code
        path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")
        print(f"backfill_run_codes: {path.name} -> {run_code}")
        touched.append(path.name)
    return touched


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be updated, without writing or minting codes.",
    )
    args = parser.parse_args()

    touched = backfill(args.history_dir, dry_run=args.dry_run)
    verb = "would update" if args.dry_run else "updated"
    print(f"backfill_run_codes: {verb} {len(touched)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

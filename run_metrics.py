"""Measured numbers for a test, kept alongside pass/fail in the run history.

Step 2 of docs/wan-integration-plan.md. A test fills a RunMetrics (via the
`run_metrics` fixture in conftest.py) with what it configured, what each
box measured, and named checks (expected vs measured). On teardown the
full record, per-second series included, is written to
results/metrics/<test-slug>-<utc>.json, and that path rides along as the
junit property `metrics`. scripts/collect_run.py then copies everything
except the series into results/history/<run>.json, so history stays small
and the series stay in the (git-ignored) sidecar file.

Shape:
    {"test": nodeid, "written-at": iso,
     "impairment": {...},                      # what the emulator was set to
     "runs": [{"label": "baseline", "ntg": {...}, "wan": {...},
               "series": {...}}],              # series: sidecar only
     "checks": [{"name", "expected", "measured", "tolerance", "unit",
                 "ok", "enforced"}]}
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).parent
METRICS_DIR = ROOT / "results" / "metrics"

# Saved-run fields worth keeping in history (the rest stays in the sidecar).
_SUMMARY_KEYS = (
    "tx-rate", "rx-rate", "tx-frames", "rx-frames", "loss-frames", "loss-pct",
    "avg-latency", "min-latency", "max-latency", "avg-jitter", "max-jitter", "duration",
)
_DIRECTION_KEYS = (
    "from-port", "to-port", "tx-frames", "rx-frames", "dropped", "loss-pct",
    "avg-latency", "min-latency", "max-latency", "avg-jitter",
)
_PORT_KEYS = (
    "port-id", "avg-tx-rate", "avg-rx-rate", "tx-frames", "rx-frames", "dropped",
    "loss-pct", "avg-latency", "nic-tx-errors", "nic-rx-errors", "rx-missed", "rx-no-mbuf",
)


def _pick(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if k in d}


def ntg_run_digest(run: dict) -> dict:
    """The parts of an NTG saved run (NtgApi.run()) that go into history.
    Latencies/jitter are in µs, as the NTG reports them."""
    directions = [
        _pick(d, _DIRECTION_KEYS)
        for flow in run.get("flow") or []
        for d in flow.get("direction") or []
    ]
    return {
        "run-id": run.get("run-id"),
        "number": run.get("number"),
        "end-reason": run.get("end-reason"),
        "tail-not-settled": run.get("tail-not-settled"),
        "stages": run.get("stages"),
        "summary": _pick(run.get("summary") or {}, _SUMMARY_KEYS),
        "port": [_pick(p, _PORT_KEYS) for p in run.get("port") or []],
        "direction": directions,
    }


class RunMetrics:
    def __init__(self, nodeid: str):
        self.record = {"test": nodeid, "impairment": None, "runs": [], "checks": []}

    def set_impairment(self, impairment: dict) -> None:
        self.record["impairment"] = impairment

    def add_run(self, label: str, ntg: dict = None, wan: dict = None, series: dict = None) -> dict:
        run = {"label": label, "ntg": ntg, "wan": wan, "series": series}
        self.record["runs"].append(run)
        return run

    def check(self, name, expected, measured, tolerance=None, unit="", enforced=True) -> bool:
        """Record expected vs measured. `tolerance` is absolute; None means
        exact. Unenforced checks are reported but never fail a test (used
        while a check's tolerance or meaning is still being established)."""
        ok = (
            measured is not None
            and expected is not None
            and abs(measured - expected) <= (tolerance or 0)
        )
        self.record["checks"].append({
            "name": name, "expected": expected, "measured": measured,
            "tolerance": tolerance, "unit": unit, "ok": ok, "enforced": enforced,
        })
        return ok

    def failed_checks(self) -> list:
        return [c for c in self.record["checks"] if c["enforced"] and not c["ok"]]

    def write(self, slug: str) -> pathlib.Path:
        now = datetime.now(timezone.utc)
        self.record["written-at"] = now.isoformat()
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        path = METRICS_DIR / f"{slug}-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(self.record, indent=1, default=str))
        return path


def history_digest(record: dict) -> dict:
    """The record minus per-second series: what run history stores."""
    digest = {k: v for k, v in record.items() if k != "runs"}
    digest["runs"] = [{k: v for k, v in run.items() if k != "series"} for run in record["runs"]]
    return digest

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
import re
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
_FLOW_KEYS = ("flow-id", "name", "stream", "protocol")
# Order/duplicate counters, by name ("late" as a whole word: not "latency").
SEQUENCE_KEY = re.compile(r"order|dup|\blate\b|seq", re.I)
_PORT_KEYS = (
    "port-id", "avg-tx-rate", "avg-rx-rate", "tx-frames", "rx-frames", "dropped",
    "loss-pct", "avg-latency", "nic-tx-errors", "nic-rx-errors", "rx-missed", "rx-no-mbuf",
)


def _pick(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if k in d}


def _direction(d: dict) -> dict:
    """A saved direction's history fields, plus any counter about order or
    duplicates the NTG reports (names not documented; T18b looks for them)."""
    picked = _pick(d, _DIRECTION_KEYS)
    picked.update({k: v for k, v in d.items()
                   if SEQUENCE_KEY.search(k) and isinstance(v, (int, float, bool))})
    return picked


def ntg_run_digest(run: dict) -> dict:
    """The parts of an NTG saved run (NtgApi.run()) that go into history.
    Latencies/jitter are in µs, as the NTG reports them. `direction` is
    every flow's directions in one list; `flow` keeps them per flow (one
    flow per stream), for tests that send streams different ways (T21)."""
    flows = [
        {**_pick(flow, _FLOW_KEYS), "direction": [_direction(d) for d in flow.get("direction") or []]}
        for flow in run.get("flow") or []
    ]
    directions = [d for flow in flows for d in flow["direction"]]
    return {
        "run-id": run.get("run-id"),
        "number": run.get("number"),
        "end-reason": run.get("end-reason"),
        "tail-not-settled": run.get("tail-not-settled"),
        "stages": run.get("stages"),
        "summary": _pick(run.get("summary") or {}, _SUMMARY_KEYS),
        "port": [_pick(p, _PORT_KEYS) for p in run.get("port") or []],
        "direction": directions,
        "flow": flows,
    }


def capture_ntg_run(api, testbed: str, run_id: str = None):
    """(digest, saved run, stored config) for `testbed`'s latest saved run,
    or `run_id`. Reads only /runs and /tests, never live /stats. The
    digest gains `configured-ports` (rate-mbps per port) and the summary
    fields the dashboard's Expand panel shows."""
    if run_id is None:
        latest = api.latest_run(testbed)
        if latest is None:
            raise AssertionError(f"{testbed}: the Controller has no saved run")
        run_id = latest["run-id"]
    saved = api.run(testbed, run_id)
    config = api.test(testbed)
    digest = ntg_run_digest(saved)
    digest["verdict"] = saved.get("verdict")
    digest["criteria"] = saved.get("criteria")
    digest["duration-sec"] = saved.get("duration-sec")
    digest["configured-ports"] = [
        {k: p.get(k) for k in ("port-id", "rate-mbps", "speed-mbps")} for p in config.get("port", [])
    ]
    return digest, saved, config


def standard_checks(metrics, label: str, digest: dict, expected_seconds: float = None,
                    expect_traffic: bool = True, expect_loss: bool = False) -> None:
    """The checks every traffic test gets, so a run can't "pass" without
    doing anything (the NTG's own verdict is "pass" with `criteria: null`).

    Enforced: traffic was sent and received. Recorded only, until a
    PASS/FAIL threshold is agreed: loss % (skipped when the run loses
    frames on purpose, e.g. through an impaired WAN path, whose own checks
    judge the loss), each port's average TX vs its configured rate, and
    the run's length."""
    s = digest.get("summary") or {}
    if expect_traffic:
        metrics.at_least(f"{label}: frames sent", minimum=1, measured=s.get("tx-frames"), unit="frames")
        metrics.at_least(f"{label}: frames received", minimum=1, measured=s.get("rx-frames"),
                         unit="frames")
    if not expect_loss:
        metrics.check(f"{label}: loss %", expected=0.0, measured=s.get("loss-pct"), tolerance=0.01,
                      unit="%", enforced=False)
    actual = {p["port-id"]: p.get("avg-tx-rate") for p in digest.get("port") or []}
    for port in digest.get("configured-ports") or []:
        rate = port.get("rate-mbps")
        if rate and port["port-id"] in actual:
            metrics.check(f"{label}: NTG Port {port['port-id']} avg TX = configured rate",
                          expected=rate, measured=actual[port["port-id"]], tolerance=rate * 0.15,
                          unit="Mbps", enforced=False)
    if expected_seconds:
        metrics.check(f"{label}: run length", expected=expected_seconds,
                      measured=_run_length(digest), tolerance=3, unit="s", enforced=False)


def _run_length(digest: dict):
    """Ramp-up + main + ramp-down from the saved run's stages, which is what
    a spec's run_seconds configures. The saved `duration-sec` counts the
    main (hold) stage only: 20 for a 2/20/2 ramp."""
    stages = digest.get("stages") or {}
    parts = [stages.get(k) for k in ("ramp-up-sec", "main-sec", "ramp-down-sec")]
    if any(p is None for p in parts):
        return digest.get("duration-sec")
    return round(sum(parts), 3)


class RunMetrics:
    def __init__(self, nodeid: str):
        self.record = {"test": nodeid, "unit": None, "impairment": None, "runs": [], "checks": []}

    def set_unit(self, unit: dict) -> None:
        """Which box and build the run was on (model, version, target)."""
        self.record["unit"] = unit

    def set_impairment(self, impairment: dict) -> None:
        self.record["impairment"] = impairment

    def add_run(self, label: str, ntg: dict = None, wan: dict = None, series: dict = None) -> dict:
        run = {"label": label, "ntg": ntg, "wan": wan, "series": series}
        self.record["runs"].append(run)
        return run

    def attach(self, label: str, wan: dict = None, series: dict = None) -> None:
        """Add emulator data (and its series) to the latest run called `label`."""
        run = next(r for r in reversed(self.record["runs"]) if r["label"] == label)
        if wan is not None:
            run["wan"] = wan
        if series:
            run["series"] = {**(run.get("series") or {}), **series}

    def check(self, name, expected, measured, tolerance=None, unit="", enforced=True) -> bool:
        """Record expected vs measured. `tolerance` is absolute; None means
        exact. Text values (a verdict) must match exactly. Unenforced checks
        are reported but never fail a test (used while a check's tolerance
        or meaning is still being established)."""
        if _is_number(expected) and _is_number(measured):
            ok = abs(measured - expected) <= (tolerance or 0)
        else:
            ok = measured is not None and measured == expected
        self.record["checks"].append({
            "name": name, "expected": expected, "measured": measured,
            "tolerance": tolerance, "unit": unit, "ok": ok, "enforced": enforced,
        })
        return ok

    def at_least(self, name, minimum, measured, unit="", enforced=True) -> bool:
        """Record measured >= minimum (shown as "≥ minimum" on the dashboard)."""
        ok = measured is not None and measured >= minimum
        self.record["checks"].append({
            "name": name, "expected": minimum, "measured": measured, "tolerance": None,
            "kind": "min", "unit": unit, "ok": ok, "enforced": enforced,
        })
        return ok

    def at_most(self, name, maximum, measured, unit="", enforced=True) -> bool:
        """Record measured <= maximum (shown as "≤ maximum" on the dashboard)."""
        ok = measured is not None and measured <= maximum
        self.record["checks"].append({
            "name": name, "expected": maximum, "measured": measured, "tolerance": None,
            "kind": "max", "unit": unit, "ok": ok, "enforced": enforced,
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


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def history_digest(record: dict) -> dict:
    """The record minus per-second series: what run history stores."""
    digest = {k: v for k, v in record.items() if k != "runs"}
    digest["runs"] = [{k: v for k, v in run.items() if k != "series"} for run in record["runs"]]
    return digest

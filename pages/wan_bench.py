"""The NTG and the WAN emulator as one bench: NTG Port 3 -> emulator
Engine 2 -> NTG Port 4. Every run through it is a known-answer test: we set
what the network does, the NTG has to report it back, and two independent
witnesses must agree (the emulator counts what it did to each frame, the
NTG what it saw).

    base = wan_bench.baseline(TESTBED, SPEC)           # Engine 2 bypass
    run = wan_bench.impaired(TESTBED, SPEC, PATH)      # through PATH
    wan_bench.check_delay(run, base, PATH)
    wan_bench.assert_ok()

Each run records onto the summary sheet: the NTG's saved run (via
TrafficEngine), Engine 2's counters for the path the traffic took, and the
checks every bench run gets (UI latency card = saved run, emulator frames =
NTG frames). The emulator is configured through its UI (WanEmulatorPage);
WanApi only reads.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

from pages.traffic_engine import RunResult, TrafficEngine
from pages.wan_emulator_page import WanEmulatorPage
from pages.wan_path_spec import WanPathSpec

# Tolerances from docs/wan-integration-plan.md §7.3 (still to be confirmed
# by Travis): latency ±5 % or ±0.5 ms, whichever is larger.
LATENCY_TOLERANCE_PCT = 5
LATENCY_TOLERANCE_FLOOR_MS = 0.5
# The UI card shows 3 decimals of the saved run's µs value.
UI_CARD_TOLERANCE_MS = 0.001
# A frame can't arrive before its delay; allow for timestamp granularity.
MIN_LATENCY_SLACK_MS = 0.05
# ARP and other control frames also cross the emulator.
FRAME_TOLERANCE = 0.005
# Counter fields that identify a flow rather than count anything.
_ID_FIELDS = ("index", "direction", "first")
_DIRECTIONS = {True: "a-to-b", False: "b-to-a"}   # keyed by from_port < to_port


def latency_tolerance_ms(expected_ms: float) -> float:
    return max(expected_ms * LATENCY_TOLERANCE_PCT / 100, LATENCY_TOLERANCE_FLOOR_MS)


@dataclass
class WanRun:
    """One NTG run through the bench, with both boxes' numbers."""
    label: str
    test: str              # node id of the test that measured it
    result: RunResult
    wan_delta: Dict[str, dict]   # emulator counter growth, per a-to-b / b-to-a

    @property
    def directions(self) -> List[Tuple[int, int]]:
        return [(d["from-port"], d["to-port"]) for d in self.result.ntg["direction"]]

    def latency_ms(self, from_port: int, to_port: int, stat: str = "avg-latency") -> float:
        """The NTG's measured one-way latency for one direction (saved in µs)."""
        for d in self.result.ntg["direction"]:
            if (d["from-port"], d["to-port"]) == (from_port, to_port):
                return d[stat] / 1000
        raise KeyError(f"no NTG direction {from_port}->{to_port} in {self.label}")

    def emulator(self, from_port: int, to_port: int) -> dict:
        return self.wan_delta.get(_DIRECTIONS[from_port < to_port]) or {}


class WanBench:
    # Baselines measured this session, keyed by testbed and spec: one
    # bypass run serves every impaired run of the same config.
    _baselines: Dict[str, WanRun] = {}

    def __init__(self, engine: TrafficEngine, emulator: WanEmulatorPage, api, metrics, test: str):
        self.engine, self.emulator, self.api, self.metrics, self.test = (
            engine, emulator, api, metrics, test
        )
        self.runs: List[WanRun] = []
        self.engine_index = emulator.ENGINE_INDEX

    # --- runs -----------------------------------------------------------
    def baseline(self, testbed: str, spec) -> WanRun:
        """The spec run with Engine 2 in bypass, or this session's earlier
        measurement of it (recorded as reused)."""
        key = f"{testbed}|{spec!r}"
        cached = self._baselines.get(key)
        if cached:
            self.metrics.add_run("baseline", ntg=cached.result.ntg,
                                 wan={"reused-from": cached.test, "delta": cached.wan_delta})
            self.runs.append(cached)
            return cached
        self.emulator.open_engine()
        self.emulator.require_idle()
        run = self._measured_run("baseline", testbed, spec, path_label="Bypass")
        if run.result.verdict == "pass":
            self._baselines[key] = run
        return run

    def impaired(self, testbed: str, spec, path: WanPathSpec) -> WanRun:
        """The spec run with all Port 3 <-> 4 traffic through `path`."""
        self.metrics.set_impairment(path.describe(self.engine_index))
        with self.emulator.applied(path):
            self._assert_saved_as_asked(path)
            return self._measured_run(path.name, testbed, spec, path_label=path.name)

    def _assert_saved_as_asked(self, path: WanPathSpec) -> None:
        """The emulator saves asynchronously and silently; confirm the path
        it stored is the one the form was given."""
        saved = next(
            (p for p in self.api.engine(self.engine_index).get("path", []) if p["label"] == path.name),
            None,
        )
        assert saved is not None, f"emulator has no path {path.name!r} after Create Path"
        wrong = path.mismatches(saved)
        assert not wrong, f"emulator saved path {path.name!r} differently: {wrong}"

    def _measured_run(self, label: str, testbed: str, spec, path_label: str) -> WanRun:
        api, engine = self.api, self.engine_index
        index = api.path_index(engine, path_label)
        before = api.flows(engine, [index])
        start = api.stats_summary(engine, [index])["current"]
        buffers_before = api.engine(engine)["status"]["buffers"]["failures"]

        result = self.engine.run(testbed, spec, label=label)

        after = api.flows(engine, [index])
        end = api.stats_summary(engine, [index])["current"]
        buffers_after = api.engine(engine)["status"]["buffers"]["failures"]
        delta = {flow_key[1]: _growth(before.get(flow_key), flow) for flow_key, flow in after.items()}
        self.metrics.attach(
            label,
            wan={"engine": engine, "path": path_label, "path-index": index, "delta": delta,
                 "buffer-failures": buffers_after - buffers_before, "seq": [start, end]},
            series={"wan": self._series(index, start, end)},
        )
        run = WanRun(label, self.test, result, delta)
        self.runs.append(run)
        self._check_ui_latency_card(run, testbed)
        self._check_frame_accounting(run)
        self.metrics.check(f"{label}: emulator buffer failures during the run", expected=0,
                           measured=buffers_after - buffers_before, unit="", enforced=False)
        return run

    def _series(self, index: int, start: int, end: int):
        """Per-second emulator records. Best-effort: charts are nice to
        have and must never fail a test."""
        try:
            return self.api.stats_records(self.engine_index, [index], start=start, end=end).get("data")
        except Exception as exc:
            return {"error": str(exc)}

    # --- checks every run gets -----------------------------------------
    def _check_ui_latency_card(self, run: WanRun, testbed: str) -> None:
        """The Statistics page's Avg Latency card shows the saved run's number."""
        self.engine.dashboard.open()
        self.engine.dashboard.open_stats(testbed)
        self.metrics.check(
            f"{run.label}: Avg Latency card = saved run",
            expected=round(run.result.ntg["summary"]["avg-latency"] / 1000, 3),
            measured=self.engine.runs.last_run_avg_latency_ms(),
            tolerance=UI_CARD_TOLERANCE_MS, unit="ms",
        )

    def _check_frame_accounting(self, run: WanRun) -> None:
        """Two witnesses: frames the emulator carried each way = frames the
        NTG sent that way."""
        for from_port, to_port in run.directions:
            sent = next(d["tx-frames"] for d in run.result.ntg["direction"]
                        if (d["from-port"], d["to-port"]) == (from_port, to_port))
            self.metrics.check(
                f"{run.label}: emulator frames {from_port}→{to_port} = NTG frames sent",
                expected=sent, measured=run.emulator(from_port, to_port).get("frames"),
                tolerance=sent * FRAME_TOLERANCE, unit="frames",
            )

    # --- impairment checks ---------------------------------------------
    def check_delay(self, run: WanRun, baseline: WanRun, path: WanPathSpec) -> None:
        """Constant delay, per direction: the NTG's average latency rises by
        the configured delay, no frame arrives sooner than the delay, and the
        emulator dropped nothing (delay alone never should)."""
        for from_port, to_port in run.directions:
            delay = path.impairment(from_port, to_port).delay_ms
            name = f"{run.label}: {from_port}→{to_port}"
            added = run.latency_ms(from_port, to_port) - baseline.latency_ms(from_port, to_port)
            self.metrics.check(f"{name} avg latency added", expected=delay, measured=round(added, 3),
                               tolerance=latency_tolerance_ms(delay), unit="ms")
            self.metrics.at_least(f"{name} min latency", minimum=delay - MIN_LATENCY_SLACK_MS,
                                  measured=run.latency_ms(from_port, to_port, "min-latency"),
                                  unit="ms")
            spread = (run.latency_ms(from_port, to_port, "max-latency")
                      - run.latency_ms(from_port, to_port, "min-latency"))
            base_spread = (baseline.latency_ms(from_port, to_port, "max-latency")
                           - baseline.latency_ms(from_port, to_port, "min-latency"))
            # Constant delay shouldn't widen the spread much; recorded until
            # there's data on how much the emulator itself adds.
            self.metrics.check(f"{name} latency spread (max - min) vs baseline",
                               expected=round(base_spread, 3), measured=round(spread, 3),
                               tolerance=latency_tolerance_ms(delay), unit="ms", enforced=False)
            self.metrics.check(f"{name} emulator WAN drops", expected=0,
                               measured=(run.emulator(from_port, to_port).get("wan") or {}).get("drops"),
                               unit="frames")

    def assert_ok(self) -> None:
        """Every run passed (NTG verdict + traffic flowed) and every
        enforced check on the summary sheet holds."""
        # Not RunResult.assert_passed(): a reused baseline's result carries
        # the summary sheet of the test that measured it, not this one.
        verdicts = {run.label: run.result.verdict for run in self.runs}
        failed = self.metrics.failed_checks()
        assert set(verdicts.values()) == {"pass"} and not failed, (
            f"NTG verdicts {verdicts}; failed checks "
            + "; ".join(f"{c['name']}: expected {c['expected']}, measured {c['measured']}"
                        for c in failed)
        )


def _growth(before, after):
    """Counter growth between two WanApi.flows() entries: numbers
    subtracted, nested dicts recursed, identifiers and text kept as-is."""
    if isinstance(after, dict):
        return {k: (v if k in _ID_FIELDS else _growth((before or {}).get(k), v))
                for k, v in after.items()}
    if isinstance(after, (int, float)) and isinstance(before, (int, float)) \
            and not isinstance(after, bool):
        return after - before
    return after

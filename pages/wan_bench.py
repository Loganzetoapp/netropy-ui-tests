"""The NTG and the WAN emulator as one bench: NTG Port 3 -> emulator
Engine 2 -> NTG Port 4. Every run through it is a known-answer test: we set
what the network does, the NTG has to report it back, and two independent
witnesses must agree (the emulator counts what it did to each frame, the
NTG what it saw).

    base = wan_bench.baseline(TESTBED, SPEC)           # Engine 2 bypass
    run = wan_bench.impaired(TESTBED, SPEC, PATH)      # through PATH
    wan_bench.check_delay(run, base, PATH)             # or check_loss / check_bandwidth
    wan_bench.assert_ok()

Each run records onto the summary sheet: the NTG's saved run (via
TrafficEngine), Engine 2's counters for the path the traffic took, and the
checks every bench run gets (UI latency card = saved run, emulator frames =
NTG frames). The emulator is configured through its UI (WanEmulatorPage);
WanApi only reads.

A path that loses frames by design (random loss, or a cap below the
offered rate) makes the NTG's default, loss-based verdict meaningless, so
those runs aren't required to "pass"; check_verdict() tests the verdict
with explicit criteria instead.
"""
from dataclasses import dataclass, replace
from statistics import median
from typing import Dict, List, Optional, Tuple

from pages import settings
from pages.traffic_engine import RunResult, TrafficEngine
from pages.wan_emulator_page import WanEmulatorPage
from pages.wan_path_spec import WanPathSpec
from pages.wan_preflight import WanPreflight

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
# ...and a handful go missing even in bypass (2 of 902,220 on 2026-10-13),
# so frame-for-frame comparisons get at least this much slack.
MIN_FRAME_SLACK = 10
# Loss ±0.2 percentage points, throughput ±2 % (plan §7.3, to be confirmed).
LOSS_TOLERANCE_PP = 0.2
THROUGHPUT_TOLERANCE_PCT = 2
# A cap's "auto" queue is drop-tail sized to 250 ms of the cap's bandwidth
# (emulator manual), so a saturated link adds about that much latency.
AUTO_QUEUE_MS = 250
# Steady state: per-second samples from this long after ramp-up ends to
# one second before ramp-down starts (queues and rates have settled).
STEADY_SETTLE_S = 2
# Counter fields that identify a flow rather than count anything.
_ID_FIELDS = ("index", "direction", "first")
_DIRECTIONS = {True: "a-to-b", False: "b-to-a"}   # keyed by from_port < to_port


def latency_tolerance_ms(expected_ms: float) -> float:
    return max(expected_ms * LATENCY_TOLERANCE_PCT / 100, LATENCY_TOLERANCE_FLOOR_MS)


def frame_tolerance(frames) -> float:
    return max((frames or 0) * FRAME_TOLERANCE, MIN_FRAME_SLACK)


@dataclass
class WanRun:
    """One NTG run through the bench, with both boxes' numbers."""
    label: str
    test: str              # node id of the test that measured it
    result: RunResult
    wan_delta: Dict[str, dict]   # emulator counter growth, per a-to-b / b-to-a
    loses_frames: bool = False   # the path drops frames by design

    @property
    def directions(self) -> List[Tuple[int, int]]:
        return [(d["from-port"], d["to-port"]) for d in self.result.ntg["direction"]]

    def direction(self, from_port: int, to_port: int) -> dict:
        """The NTG's saved totals for one direction (frames, loss, latency)."""
        for d in self.result.ntg["direction"]:
            if (d["from-port"], d["to-port"]) == (from_port, to_port):
                return d
        raise KeyError(f"no NTG direction {from_port}->{to_port} in {self.label}")

    def latency_ms(self, from_port: int, to_port: int, stat: str = "avg-latency") -> float:
        """The NTG's measured one-way latency for one direction (saved in µs)."""
        return self.direction(from_port, to_port)[stat] / 1000

    def steady_mbps(self, port: int, stat: str) -> Optional[float]:
        """Median per-second `stat` ("tx-rate"/"rx-rate", Mbps) of NTG
        `port` over the run's steady state. The run averages include the
        ramps, so a rate check reads the saved per-second samples."""
        stages = self.result.ntg.get("stages") or {}
        start = (stages.get("ramp-up-sec") or 0) + STEADY_SETTLE_S
        end = (stages.get("ramp-up-sec") or 0) + (stages.get("main-sec") or 0) - 1
        values = [p[stat] for sample in self.result.samples or []
                  if start <= sample.get("at", -1) <= end
                  for p in sample.get("port") or [] if p.get("port-id") == port and stat in p]
        return round(median(values), 3) if len(values) >= 3 else None

    def emulator(self, from_port: int, to_port: int) -> dict:
        return self.wan_delta.get(_DIRECTIONS[from_port < to_port]) or {}


class WanBench:
    # Baselines measured this session, keyed by testbed and spec: one
    # bypass run serves every impaired run of the same config.
    _baselines: Dict[str, WanRun] = {}

    def __init__(self, engine: TrafficEngine, emulator: WanEmulatorPage, api, metrics, test: str,
                 lease=None):
        self.engine, self.emulator, self.api, self.metrics, self.test = (
            engine, emulator, api, metrics, test
        )
        self.runs: List[WanRun] = []
        self.engine_index = emulator.ENGINE_INDEX
        self.lease = lease
        self._ready = False

    def _preflight(self, testbed: str, spec) -> None:
        """Pre-run checks and set-up (pages/wan_preflight.py), once per test."""
        if not self._ready:
            WanPreflight(self.emulator, self.api, self.metrics, self.lease).run(testbed, spec)
            self._ready = True

    # --- runs -----------------------------------------------------------
    def baseline(self, testbed: str, spec) -> WanRun:
        """The spec run with Engine 2 in bypass, or this session's earlier
        measurement of it (recorded as reused)."""
        self._preflight(testbed, spec)
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
        self._preflight(testbed, spec)
        self.metrics.set_impairment(path.describe(self.engine_index))
        lossy = any(
            path.impairment(sender, receiver).loses_frames(spec.ports[sender].rate_mbps)
            for sender in spec.ports for receiver in spec.ports if sender != receiver
        )
        if lossy:
            spec = replace(spec, expect_loss=True)
        with self.emulator.applied(path):
            self._assert_saved_as_asked(path)
            return self._measured_run(path.name, testbed, spec, path_label=path.name,
                                      loses_frames=lossy)

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

    def _measured_run(self, label: str, testbed: str, spec, path_label: str,
                      loses_frames: bool = False) -> WanRun:
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
        run = WanRun(label, self.test, result, delta, loses_frames)
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
        """Two witnesses, each way. The emulator's `frames` counts what it
        *delivered* and `drops` everything it dropped (WAN loss and queue
        tail-drops alike), so: delivered = what the NTG received, and
        delivered + dropped = what the NTG sent (confirmed exact on T16/T17,
        2026-10-16)."""
        for from_port, to_port in run.directions:
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            delivered, dropped = emu.get("frames"), emu.get("drops") or 0
            name = f"{run.label}: {from_port}→{to_port}"
            self.metrics.check(f"{name} emulator frames delivered = NTG frames received",
                               expected=ntg["rx-frames"], measured=delivered,
                               tolerance=frame_tolerance(ntg["rx-frames"]), unit="frames")
            self.metrics.check(f"{name} emulator frames delivered + dropped = NTG frames sent",
                               expected=ntg["tx-frames"],
                               measured=None if delivered is None else delivered + dropped,
                               tolerance=frame_tolerance(ntg["tx-frames"]), unit="frames")

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

    def check_loss(self, run: WanRun, baseline: WanRun, path: WanPathSpec) -> None:
        """Random loss, per direction: the NTG's loss % is the configured
        rate, the frames it lost are the ones the emulator dropped (two
        witnesses, frame for frame), and loss alone adds no latency."""
        for from_port, to_port in run.directions:
            rate = path.impairment(from_port, to_port).loss_pct
            name = f"{run.label}: {from_port}→{to_port}"
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            wan_drops = (emu.get("wan") or {}).get("drops")
            self.metrics.check(f"{name} NTG loss %", expected=rate, measured=ntg.get("loss-pct"),
                               tolerance=LOSS_TOLERANCE_PP, unit="%")
            self.metrics.check(f"{name} NTG frames lost = emulator WAN drops", expected=wan_drops,
                               measured=ntg.get("dropped"), tolerance=frame_tolerance(wan_drops),
                               unit="frames")
            # The emulator's own accuracy: says which box is off when the
            # NTG check above fails.
            entered = (emu.get("frames") or 0) + (emu.get("drops") or 0)
            self.metrics.check(f"{name} emulator drop rate", expected=rate,
                               measured=_pct(wan_drops, entered),
                               tolerance=LOSS_TOLERANCE_PP, unit="%", enforced=False)
            added = run.latency_ms(from_port, to_port) - baseline.latency_ms(from_port, to_port)
            self.metrics.check(f"{name} avg latency added (loss adds none)", expected=0,
                               measured=round(added, 3), tolerance=LATENCY_TOLERANCE_FLOOR_MS,
                               unit="ms")

    def check_bandwidth(self, run: WanRun, baseline: WanRun, path: WanPathSpec) -> None:
        """Access-link cap, per direction. Below the offered rate, the
        receiver gets the cap, the excess is tail-dropped at the cap's
        queue (the NTG's lost frames = the emulator's queue drops), and
        the full queue adds its depth in latency. Above it, the link must
        be invisible: everything arrives, at the offered rate, on time."""
        configured = {p["port-id"]: p.get("rate-mbps")
                      for p in run.result.ntg.get("configured-ports") or []}
        for from_port, to_port in run.directions:
            cap = path.impairment(from_port, to_port).bandwidth_mbps
            if not cap:
                continue
            name = f"{run.label}: {from_port}→{to_port}"
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            offered = run.steady_mbps(from_port, "tx-rate")
            received = run.steady_mbps(to_port, "rx-rate")
            queue_drops = ((emu.get("inflow") or {}).get("queue") or {}).get("drops")
            self.metrics.check(f"{name} emulator WAN drops (a cap drops at its queue)", expected=0,
                               measured=(emu.get("wan") or {}).get("drops"), unit="frames")
            if cap < (configured.get(from_port) or 0):
                self.metrics.check(f"{name} received rate = {cap:g} Mbps cap (steady state)",
                                   expected=cap, measured=received,
                                   tolerance=cap * THROUGHPUT_TOLERANCE_PCT / 100, unit="Mbps")
                self.metrics.check(f"{name} NTG frames lost = emulator queue drops",
                                   expected=queue_drops, measured=ntg.get("dropped"),
                                   tolerance=frame_tolerance(queue_drops), unit="frames")
                added = (run.latency_ms(from_port, to_port, "max-latency")
                         - baseline.latency_ms(from_port, to_port, "max-latency"))
                # Recorded until the "auto" queue's real depth is measured.
                self.metrics.check(f"{name} max latency added = full auto queue", expected=AUTO_QUEUE_MS,
                                   measured=round(added, 3), tolerance=AUTO_QUEUE_MS * 0.1,
                                   unit="ms", enforced=False)
            else:
                self.metrics.check(f"{name} received rate = offered (cap {cap:g} Mbps, steady state)",
                                   expected=offered, measured=received,
                                   tolerance=(offered or 0) * THROUGHPUT_TOLERANCE_PCT / 100,
                                   unit="Mbps")
                self.metrics.check(f"{name} emulator queue drops", expected=0, measured=queue_drops,
                                   unit="frames")
                self.metrics.check(f"{name} NTG frames lost", expected=0, measured=ntg.get("dropped"),
                                   tolerance=MIN_FRAME_SLACK, unit="frames")
                added = run.latency_ms(from_port, to_port) - baseline.latency_ms(from_port, to_port)
                self.metrics.check(f"{name} avg latency added (no standing queue)", expected=0,
                                   measured=round(added, 3), tolerance=LATENCY_TOLERANCE_FLOOR_MS,
                                   unit="ms")

    def check_verdict(self, run: WanRun, testbed: str, max_loss_pct: float) -> None:
        """The NTG's own pass/fail rule on a saved run: set Max loss through
        the run's "Edit pass criteria" popover, then the verdict must follow
        the run's measured loss, on screen and in the Controller, which
        must also have stored the threshold as typed."""
        from ntg_api import NtgApi

        measured = run.result.ntg["summary"]["loss-pct"]
        assert abs(measured - max_loss_pct) > LOSS_TOLERANCE_PP, (
            f"max loss {max_loss_pct} % is too close to the measured {measured} % "
            "for the expected verdict to be certain; pick a threshold further away"
        )
        expected = "fail" if measured > max_loss_pct else "pass"
        number, run_id = run.result.ntg["number"], run.result.ntg["run-id"]
        self.engine.dashboard.open()
        self.engine.dashboard.open_stats(testbed)
        self.engine.runs.set_pass_criteria(number, max_loss_pct=max_loss_pct)
        shown = self.engine.runs.verdict_once(self.engine.runs.run_row(number), expected)

        api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
        name = f"{run.label}: max loss {max_loss_pct:g} % on a {measured:.3f} % run"
        self.metrics.check(f"{name}, Controller stores the threshold", expected=max_loss_pct,
                           measured=api.run_criteria(testbed, run_id).get("max-loss-pct"), unit="%")
        self.metrics.check(f"{name}, verdict on screen", expected=expected, measured=shown)
        self.metrics.check(f"{name}, verdict in the Controller", expected=expected,
                           measured=api.run(testbed, run_id).get("verdict"))

    def assert_ok(self) -> None:
        """Every run passed (NTG verdict + traffic flowed) and every
        enforced check on the summary sheet holds. Runs through a path
        that loses frames by design are exempt from the verdict: the NTG's
        default criterion is loss-based (see check_verdict)."""
        # Not RunResult.assert_passed(): a reused baseline's result carries
        # the summary sheet of the test that measured it, not this one.
        verdicts = {run.label: run.result.verdict for run in self.runs}
        judged = {run.result.verdict for run in self.runs if not run.loses_frames}
        failed = self.metrics.failed_checks()
        assert judged <= {"pass"} and not failed, (
            f"NTG verdicts {verdicts}; failed checks "
            + "; ".join(f"{c['name']}: expected {c['expected']}, measured {c['measured']}"
                        for c in failed)
        )


def _pct(part, whole):
    return round(100 * part / whole, 4) if part is not None and whole else None


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

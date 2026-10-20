"""The NTG and the WAN emulator as one bench: NTG Port 3 -> emulator
Engine 2 -> NTG Port 4. Every run through it is a known-answer test: we set
what the network does, the NTG has to report it back, and two independent
witnesses must agree (the emulator counts what it did to each frame, the
NTG what it saw).

    base = wan_bench.baseline(TESTBED, SPEC)           # Engine 2 bypass
    run = wan_bench.impaired(TESTBED, SPEC, PATH)      # through PATH
    wan_bench.check_delay(run, base, PATH)             # or check_loss / check_bandwidth / ...
    wan_bench.assert_ok()

Other ways to run (one check_* method each, listed in pages/README.md):
    wan_bench.impaired_with_change(TESTBED, SPEC, PATH, THEN, after_s=20)  # T19b: edit mid-run
    wan_bench.routed(TESTBED, SPEC, {0: UDP_PATH, 1: TCP_PATH})            # T21: a path per stream
    path = wan_bench.read_preset("Cellular", "LTE", "t20-lte")             # T20: preset -> spec

Each run records onto the summary sheet: the NTG's saved run (via
TrafficEngine), Engine 2's counters for the path the traffic took, and the
checks every bench run gets (UI latency card = saved run, emulator frames =
NTG frames). The emulator is configured through its UI (WanEmulatorPage);
WanApi only reads.

A path that loses frames by design (random loss, an outage, or a cap
below the offered rate), or that duplicates or reorders them, makes the
NTG's default, loss-based verdict meaningless, so those runs aren't
required to "pass"; check_verdict() tests the verdict with explicit
criteria instead.
"""
import math
import time
from dataclasses import dataclass, field, replace
from statistics import median
from typing import Callable, Dict, List, Optional, Tuple

from pages import settings
from pages.traffic_engine import RunResult, TrafficEngine
from pages.wan_emulator_page import WanEmulatorPage
from pages.wan_path_spec import EndpointSpec, NotModelled, WanPathSpec, _num
from pages.wan_preflight import WanPreflight
from run_metrics import SEQUENCE_KEY

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
# Jitter (normal delay): the mean may shift by this many σ, since the
# emulator skews delays to keep frames in order; no frame should be later
# than mean + this many σ.
JITTER_MEAN_TOLERANCE_SIGMA = 0.25
JITTER_MAX_SIGMA = 6
# Expected NTG jitter for independent normal delays, as a multiple of σ:
# E|X1 - X2| = 2σ/√π. Kept in-order delays are far from independent, so
# this is recorded, not enforced, until we know which the NTG reports.
INDEPENDENT_JITTER_PER_SIGMA = 2 / math.sqrt(math.pi)
# The NTG sends frames in bursts of this many at line rate (TX burst
# "blank = datapath default"; the field's maximum). A burst queues at a cap
# well below line rate even when the average rate fits under it: on 4G LTE
# (12.5 / 15 Mbps caps, 6.25 Mbps offered) latency rose by exactly 16.5
# frame-times at the cap both ways, the mean wait in a 32-frame burst
# (2026-10-19).
NTG_TX_BURST_FRAMES = 32
# The emulator charges each frame its size plus 4 bytes against a cap
# (1,504 B per 1,500 B NTG frame, T17a 2026-10-16).
EMULATOR_FRAME_OVERHEAD_B = 4
# Outage: a second counts as "dark" when the receiver gets under this
# fraction of the offered rate.
DARK_FRACTION = 0.1
# Mid-run change: per-second samples this close to the edit are skipped
# (the NTG's run clock starts about when Stop appears, not exactly).
SWITCH_MARGIN_S = 3
# How long a path edit (Apply Changes) gets to show up in the stored config.
EDIT_SAVE_TIMEOUT_S = 20
# Counter fields that identify a flow rather than count anything.
_ID_FIELDS = ("index", "direction", "first")
_DIRECTIONS = {True: "a-to-b", False: "b-to-a"}   # keyed by from_port < to_port


def latency_tolerance_ms(expected_ms: float) -> float:
    return max(expected_ms * LATENCY_TOLERANCE_PCT / 100, LATENCY_TOLERANCE_FLOOR_MS)


def frame_tolerance(frames) -> float:
    return max((frames or 0) * FRAME_TOLERANCE, MIN_FRAME_SLACK)


def burst_queue_ms(cap_mbps: Optional[float], frame_bytes: int) -> float:
    """Average latency an NTG burst adds queueing at a cap: the mean frame
    waits behind (burst - 1) / 2 others, plus its own transmission."""
    if not cap_mbps:
        return 0.0
    frame_ms = (frame_bytes + EMULATOR_FRAME_OVERHEAD_B) * 8 / (cap_mbps * 1000)
    return (NTG_TX_BURST_FRAMES + 1) / 2 * frame_ms


def loss_tolerance_pp(rate_pct: float, frames) -> float:
    """±LOSS_TOLERANCE_PP, widened to 3σ of the binomial when a run has too
    few frames for that to be fair (T20's low-rate preset runs)."""
    if not frames:
        return LOSS_TOLERANCE_PP
    p = rate_pct / 100
    return max(LOSS_TOLERANCE_PP, round(300 * math.sqrt(p * (1 - p) / frames), 3))


@dataclass
class WanRun:
    """One NTG run through the bench, with both boxes' numbers."""
    label: str
    test: str              # node id of the test that measured it
    result: RunResult
    wan_delta: Dict[str, dict]   # emulator counter growth, per a-to-b / b-to-a (all paths summed)
    loses_frames: bool = False   # frames dropped, duplicated or reordered by design: no verdict
    per_path: Dict[str, Dict[str, dict]] = field(default_factory=dict)  # {path label: {direction: growth}}
    marks: dict = field(default_factory=dict)   # e.g. when a mid-run edit happened

    @property
    def directions(self) -> List[Tuple[int, int]]:
        seen = []
        for d in self.result.ntg["direction"]:
            if (d["from-port"], d["to-port"]) not in seen:
                seen.append((d["from-port"], d["to-port"]))
        return seen

    def direction(self, from_port: int, to_port: int) -> dict:
        """The NTG's saved totals for one direction (frames, loss, latency),
        summed over every stream that goes that way."""
        parts = [d for d in self.result.ntg["direction"]
                 if (d["from-port"], d["to-port"]) == (from_port, to_port)]
        if not parts:
            raise KeyError(f"no NTG direction {from_port}->{to_port} in {self.label}")
        return parts[0] if len(parts) == 1 else _combine(parts)

    def flow_direction(self, flow: int, from_port: int, to_port: int) -> dict:
        """One stream's saved totals for one direction. `flow` is the
        stream's index in the spec: the NTG numbers flows in stream order."""
        for d in self.result.ntg["flow"][flow]["direction"]:
            if (d["from-port"], d["to-port"]) == (from_port, to_port):
                return d
        raise KeyError(f"no NTG flow {flow} direction {from_port}->{to_port} in {self.label}")

    def latency_ms(self, from_port: int, to_port: int, stat: str = "avg-latency") -> float:
        """The NTG's measured one-way latency for one direction (saved in µs)."""
        return self.direction(from_port, to_port)[stat] / 1000

    def steady_window(self) -> Tuple[float, float]:
        """Seconds into the run: STEADY_SETTLE_S after ramp-up ends to one
        second before ramp-down starts."""
        stages = self.result.ntg.get("stages") or {}
        up = stages.get("ramp-up-sec") or 0
        return up + STEADY_SETTLE_S, up + (stages.get("main-sec") or 0) - 1

    def series(self, port: int, stat: str, start: float = None, end: float = None
               ) -> List[Tuple[float, float]]:
        """[(seconds into the run, value)] of NTG `port`'s per-second `stat`
        between `start` and `end` (default: the steady state). Rates are
        Mbps; a port's avg-latency is µs, for traffic it *received*."""
        steady = self.steady_window()
        start = steady[0] if start is None else start
        end = steady[1] if end is None else end
        return [(sample["at"], p[stat]) for sample in self.result.samples or []
                if start <= sample.get("at", -1) <= end
                for p in sample.get("port") or [] if p.get("port-id") == port and stat in p]

    def steady_mbps(self, port: int, stat: str) -> Optional[float]:
        """Median per-second `stat` ("tx-rate"/"rx-rate", Mbps) of NTG
        `port` over the run's steady state. The run averages include the
        ramps, so a rate check reads the saved per-second samples."""
        values = [v for _, v in self.series(port, stat)]
        return round(median(values), 3) if len(values) >= 3 else None

    def emulator(self, from_port: int, to_port: int) -> dict:
        return self.wan_delta.get(_DIRECTIONS[from_port < to_port]) or {}

    def emulator_path(self, label: str, from_port: int, to_port: int) -> dict:
        return (self.per_path.get(label) or {}).get(_DIRECTIONS[from_port < to_port]) or {}


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
        run = self._measured_run("baseline", testbed, spec, ["Bypass"])
        if run.result.verdict == "pass":
            self._baselines[key] = run
        return run

    def impaired(self, testbed: str, spec, path: WanPathSpec) -> WanRun:
        """The spec run with all Port 3 <-> 4 traffic through `path`."""
        self._preflight(testbed, spec)
        self.metrics.set_impairment(path.describe(self.engine_index))
        lossy, spec = self._by_design(spec, [path])
        with self.emulator.applied(path):
            self._assert_saved_as_asked(path)
            return self._measured_run(path.name, testbed, spec, [path.name], loses_frames=lossy)

    def impaired_with_change(self, testbed: str, spec, path: WanPathSpec, change_to: WanPathSpec,
                             after_s: float) -> WanRun:
        """The spec run through `path`, which is edited to `change_to` (same
        name) `after_s` seconds after traffic starts, while it runs. The
        edit's start and end, in seconds after Start, go in run.marks."""
        assert change_to.name == path.name, "a mid-run change edits the same path"
        assert after_s + 2 * SWITCH_MARGIN_S < spec.run_seconds, (
            f"a change {after_s} s in leaves no steady state after it in a {spec.run_seconds} s run"
        )
        self._preflight(testbed, spec)
        self.metrics.set_impairment({**path.describe(self.engine_index),
                                     "then": change_to.describe(self.engine_index),
                                     "after-s": after_s})
        lossy, spec = self._by_design(spec, [path, change_to])

        def change() -> dict:
            started = time.monotonic()
            # Scheduling, not settling: the edit has to land mid-run.
            time.sleep(after_s)
            begin = time.monotonic() - started
            self.emulator.edit_path(change_to)
            self._wait_saved(change_to)
            return {"edit-start-s": round(begin, 1),
                    "edit-end-s": round(time.monotonic() - started, 1)}

        with self.emulator.applied(path):
            self._assert_saved_as_asked(path)
            return self._measured_run(path.name, testbed, spec, [path.name], loses_frames=lossy,
                                      during=change)

    def routed(self, testbed: str, spec, routes: Dict[int, WanPathSpec]) -> WanRun:
        """The spec run with each stream through its own path: `routes`
        maps a stream's index in spec.streams to a path. Endpoints match
        the stream's protocol (UDP/TCP) on both emulator ports, so routed
        streams need different protocols. Other traffic bypasses."""
        protocols = [spec.streams[i].protocol.lower() for i in routes]
        assert len(set(protocols)) == len(protocols) and set(protocols) <= {"udp", "tcp"}, (
            f"endpoints tell streams apart by protocol (udp/tcp, one each), got {protocols}"
        )
        self._preflight(testbed, spec)
        paths = list(routes.values())
        endpoints = [EndpointSpec(f"{path.name}-p{port}", port, spec.streams[i].protocol.lower(),
                                  path.name, spec.ports[port].ip)
                     for i, path in routes.items() for port in spec.port_numbers]
        self.metrics.set_impairment({
            "engine": self.engine_index,
            "routes": {f"stream {i} ({spec.streams[i].protocol})": path.describe(self.engine_index)
                       for i, path in routes.items()},
        })
        lossy, spec = self._by_design(spec, paths)
        label = "+".join(path.name for path in paths)
        with self.emulator.routed(paths, endpoints):
            for path in paths:
                self._assert_saved_as_asked(path)
            return self._measured_run(label, testbed, spec, ["Bypass"] + [p.name for p in paths],
                                      loses_frames=lossy)

    def read_preset(self, group: str, preset, name: str) -> WanPathSpec:
        """The spec a built-in preset amounts to. The preset is created as
        path `name` (never applied to traffic), read back through the API
        and deleted; the test then runs that spec like any other, so the
        bench types the preset's values into the form itself and checks
        the box stored them. Fails, naming each setting, if the preset uses
        something WanPathSpec can't describe yet."""
        self.emulator.open_engine()
        self.emulator.delete_path(name)
        try:
            self.emulator.create_path_from_preset(name, group, preset)
            saved = next(p for p in self.api.engine(self.engine_index).get("path", [])
                         if p["label"] == name)
        finally:
            self.emulator.open_engine()
            self.emulator.delete_path(name)
        try:
            spec = WanPathSpec.from_saved(saved, name)
        except NotModelled as exc:
            raise AssertionError(
                f"preset {group} / {preset} uses settings WanPathSpec can't describe yet: {exc}. "
                "Add them to Impairment (pages/wan_path_spec.py) to test this preset."
            ) from None
        self.metrics.record["preset"] = {"group": group, "preset": str(preset),
                                         "spec": spec.describe(self.engine_index)}
        return spec

    def _by_design(self, spec, paths) -> Tuple[bool, object]:
        """(whether `paths` drop, duplicate or reorder frames on purpose for
        this spec, the spec marked to expect loss when they do)."""
        lossy = any(
            imp.loses_frames(spec.ports[sender].rate_mbps) or imp.alters_sequence
            for path in paths
            for sender in spec.ports for receiver in spec.ports if sender != receiver
            for imp in [path.impairment(sender, receiver)]
        )
        return lossy, (replace(spec, expect_loss=True) if lossy else spec)

    def _stored(self, name: str) -> Optional[dict]:
        return next((p for p in self.api.engine(self.engine_index).get("path", [])
                     if p["label"] == name), None)

    def _assert_saved_as_asked(self, path: WanPathSpec) -> None:
        """The emulator saves asynchronously and silently; confirm the path
        it stored is the one the form was given."""
        saved = self._stored(path.name)
        assert saved is not None, f"emulator has no path {path.name!r} after Create Path"
        wrong = path.mismatches(saved)
        assert not wrong, f"emulator saved path {path.name!r} differently: {wrong}"

    def _wait_saved(self, path: WanPathSpec) -> None:
        """Poll until the stored path matches `path` (after an edit)."""
        deadline = time.monotonic() + EDIT_SAVE_TIMEOUT_S
        while True:
            wrong = path.mismatches(self._stored(path.name) or {})
            if not wrong:
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f"path {path.name!r} edit not saved after "
                                     f"{EDIT_SAVE_TIMEOUT_S}s: {wrong}")
            time.sleep(1)  # poll interval

    def _measured_run(self, label: str, testbed: str, spec, path_labels: List[str],
                      loses_frames: bool = False, during: Callable[[], dict] = None) -> WanRun:
        """One NTG run, with Engine 2's counters for `path_labels` diffed
        around it. `during`, if given, runs once traffic has started and
        returns marks to keep with the run."""
        api, engine = self.api, self.engine_index
        indices = {api.path_index(engine, name): name for name in path_labels}
        before = api.flows(engine, list(indices))
        start = api.stats_summary(engine, list(indices))["current"]
        buffers_before = api.engine(engine)["status"]["buffers"]["failures"]

        marks = {}
        if during is None:
            result = self.engine.run(testbed, spec, label=label)
        else:
            self.engine.create(testbed, spec)
            self.engine.start(testbed)
            marks = during()
            result = self.engine.wait(testbed, spec, label=label)

        after = api.flows(engine, list(indices))
        end = api.stats_summary(engine, list(indices))["current"]
        buffers_after = api.engine(engine)["status"]["buffers"]["failures"]
        per_path: Dict[str, Dict[str, dict]] = {}
        for (index, direction), flow in after.items():
            per_path.setdefault(indices[index], {})[direction] = _growth(before.get((index, direction)), flow)
        delta = {direction: _sum([flows[direction] for flows in per_path.values() if direction in flows])
                 for direction in ("a-to-b", "b-to-a")}
        wan = {"engine": engine, "path": "+".join(path_labels), "path-index": list(indices) if len(indices) > 1 else next(iter(indices)),
               "delta": delta, "buffer-failures": buffers_after - buffers_before, "seq": [start, end]}
        if len(path_labels) > 1:
            wan["per-path"] = per_path
        if marks:
            wan["marks"] = marks
        self.metrics.attach(label, wan=wan, series={"wan": self._series(list(indices), start, end)})
        run = WanRun(label, self.test, result, delta, loses_frames, per_path, marks)
        self.runs.append(run)
        self._check_ui_latency_card(run, testbed)
        self._check_frame_accounting(run)
        self.metrics.check(f"{label}: emulator buffer failures during the run", expected=0,
                           measured=buffers_after - buffers_before, unit="", enforced=False)
        return run

    def _series(self, indices: List[int], start: int, end: int):
        """Per-second emulator records. Best-effort: charts are nice to
        have and must never fail a test."""
        try:
            return self.api.stats_records(self.engine_index, indices, start=start, end=end).get("data")
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
        2026-10-16). Duplicates are frames the emulator made itself, so they
        come off the sent side; whether the NTG counts them as received is
        what T18b finds out, so that half is recorded, not enforced, when
        the run duplicated anything."""
        for from_port, to_port in run.directions:
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            delivered, dropped = emu.get("frames"), emu.get("drops") or 0
            duplicates = (emu.get("wan") or {}).get("duplicates") or 0
            name = f"{run.label}: {from_port}→{to_port}"
            self.metrics.check(f"{name} emulator frames delivered = NTG frames received",
                               expected=ntg["rx-frames"], measured=delivered,
                               tolerance=frame_tolerance(ntg["rx-frames"]), unit="frames",
                               enforced=not duplicates)
            self.metrics.check(f"{name} emulator frames delivered + dropped - duplicated = NTG frames sent",
                               expected=ntg["tx-frames"],
                               measured=None if delivered is None else delivered + dropped - duplicates,
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

    def check_jitter(self, run: WanRun, baseline: WanRun, path: WanPathSpec) -> None:
        """Normal-distribution delay (mean, σ), per direction: the average
        latency rises by the mean, no frame arrives later than mean + 6σ,
        none earlier than in bypass, and the emulator dropped nothing.
        The NTG's jitter must rise; how far is recorded against the
        independent-delay figure (2σ/√π), since the emulator keeps frames
        in order, which correlates neighbouring delays."""
        for from_port, to_port in run.directions:
            imp = path.impairment(from_port, to_port)
            mean, sigma = imp.delay_ms, imp.jitter_ms
            name = f"{run.label}: {from_port}→{to_port}"
            added = run.latency_ms(from_port, to_port) - baseline.latency_ms(from_port, to_port)
            self.metrics.check(f"{name} avg latency added = mean", expected=mean, measured=round(added, 3),
                               tolerance=max(latency_tolerance_ms(mean), JITTER_MEAN_TOLERANCE_SIGMA * sigma),
                               unit="ms")
            self.metrics.at_most(f"{name} max latency ≤ mean + {JITTER_MAX_SIGMA}σ",
                                 maximum=round(baseline.latency_ms(from_port, to_port, "max-latency")
                                               + mean + JITTER_MAX_SIGMA * sigma, 3),
                                 measured=run.latency_ms(from_port, to_port, "max-latency"), unit="ms")
            self.metrics.at_least(f"{name} min latency ≥ bypass min",
                                  minimum=baseline.latency_ms(from_port, to_port, "min-latency")
                                  - MIN_LATENCY_SLACK_MS,
                                  measured=run.latency_ms(from_port, to_port, "min-latency"), unit="ms")
            # 5.0.12 leaves avg-jitter out of a saved direction when it is
            # zero (the bypass baseline), so absent means 0.
            jitter = (run.direction(from_port, to_port).get("avg-jitter") or 0) / 1000
            base_jitter = (baseline.direction(from_port, to_port).get("avg-jitter") or 0) / 1000
            self.metrics.at_least(f"{name} NTG avg jitter rises above bypass", minimum=round(base_jitter, 3),
                                  measured=round(jitter, 3), unit="ms")
            expected = INDEPENDENT_JITTER_PER_SIGMA * sigma
            self.metrics.check(f"{name} NTG avg jitter added vs 2σ/√π (frames kept in order)",
                               expected=round(expected, 3), measured=round(jitter - base_jitter, 3),
                               tolerance=round(expected / 2, 3), unit="ms", enforced=False)
            self.metrics.check(f"{name} emulator WAN drops", expected=0,
                               measured=(run.emulator(from_port, to_port).get("wan") or {}).get("drops"),
                               unit="frames")

    def check_sequence(self, run: WanRun, path: WanPathSpec) -> None:
        """Duplication and reordering, per direction. Neither loses a frame,
        so the NTG must never report negative loss, nor receive more than
        it sent plus the emulator's duplicates. How it counts them is
        recorded: duplicates as extra received frames (or discarded), late
        frames as received (or lost), plus any order/duplicate counters the
        saved run has. The emulator's own rates are recorded too."""
        for from_port, to_port in run.directions:
            imp = path.impairment(from_port, to_port)
            name = f"{run.label}: {from_port}→{to_port}"
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            wan = emu.get("wan") or {}
            entered = (emu.get("frames") or 0) + (emu.get("drops") or 0) - (wan.get("duplicates") or 0)
            self.metrics.at_least(f"{name} NTG loss % not negative", minimum=0,
                                  measured=ntg.get("loss-pct"), unit="%")
            self.metrics.at_most(f"{name} NTG frames received ≤ sent + emulator duplicates",
                                 maximum=ntg["tx-frames"] + (wan.get("duplicates") or 0),
                                 measured=ntg["rx-frames"], unit="frames")
            if imp.duplicate_pct:
                self.metrics.check(f"{name} emulator duplication rate", expected=imp.duplicate_pct,
                                   measured=_pct(wan.get("duplicates"), entered),
                                   tolerance=loss_tolerance_pp(imp.duplicate_pct, entered), unit="%",
                                   enforced=False)
                self.metrics.check(f"{name} NTG extra frames received vs emulator duplicates "
                                   "(0 = NTG discards duplicates)",
                                   expected=wan.get("duplicates"),
                                   measured=ntg["rx-frames"] - ntg["tx-frames"] + (ntg.get("dropped") or 0),
                                   tolerance=frame_tolerance(wan.get("duplicates")), unit="frames",
                                   enforced=False)
            if imp.reorder_pct:
                self.metrics.check(f"{name} emulator reorder rate", expected=imp.reorder_pct,
                                   measured=_pct(wan.get("reorders"), entered),
                                   tolerance=loss_tolerance_pp(imp.reorder_pct, entered), unit="%",
                                   enforced=False)
                self.metrics.check(f"{name} NTG loss % with reordering (0 = late frames count as received)",
                                   expected=0, measured=ntg.get("loss-pct"), tolerance=LOSS_TOLERANCE_PP,
                                   unit="%", enforced=False)
            # Whatever order/duplicate counters the saved run has (names
            # undocumented; run_metrics keeps any that match), for the record.
            counters = {k: v for k, v in ntg.items() if SEQUENCE_KEY.search(k)}
            self.metrics.record.setdefault("ntg-sequence-counters", {})[name] = counters or "none reported"

    def check_outage(self, run: WanRun, path: WanPathSpec) -> None:
        """Periodic outage, per direction: the run is still saved, the
        NTG's per-second receive rate goes dark during outages, and every
        frame it lost is one the emulator dropped. How much went dark, and
        how far apart, is recorded: the outage clock starts when Emulation
        is switched on, not with the run."""
        self._check_completed(run)
        for from_port, to_port in run.directions:
            imp = path.impairment(from_port, to_port)
            name = f"{run.label}: {from_port}→{to_port}"
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            offered = run.steady_mbps(from_port, "tx-rate") or 0
            received = run.series(to_port, "rx-rate")
            dark = [at for at, rate in received if rate < DARK_FRACTION * offered]
            self.metrics.at_least(f"{name} seconds with receive rate under {DARK_FRACTION:.0%} of offered",
                                  minimum=1, measured=len(dark), unit="s")
            span = len(received)
            self.metrics.check(f"{name} dark seconds vs {_num(imp.outage_s)} s in every "
                               f"{_num(imp.outage_every_s)} s",
                               expected=round(span * imp.outage_s / imp.outage_every_s, 1),
                               measured=len(dark),
                               tolerance=math.ceil(span / imp.outage_every_s) + 1, unit="s",
                               enforced=False)
            starts = [at for i, at in enumerate(dark) if i == 0 or at - dark[i - 1] > 1.5]
            if len(starts) >= 2:
                self.metrics.check(f"{name} time between outages", expected=imp.outage_every_s,
                                   measured=round(median(b - a for a, b in zip(starts, starts[1:])), 1),
                                   tolerance=1.5, unit="s", enforced=False)
            self.metrics.check(f"{name} NTG frames lost = emulator drops", expected=emu.get("drops"),
                               measured=ntg.get("dropped"), tolerance=frame_tolerance(emu.get("drops")),
                               unit="frames")
            self.metrics.check(f"{name} NTG loss % vs outage share", expected=round(
                100 * imp.outage_s / imp.outage_every_s, 2), measured=ntg.get("loss-pct"),
                tolerance=5, unit="%", enforced=False)

    def check_change(self, run: WanRun, baseline: WanRun, before: WanPathSpec,
                     after: WanPathSpec) -> None:
        """A path edited mid-run (impaired_with_change), per direction:
        per-second latency sits at the old delay before the edit and the
        new one after it, and the run is still saved. When the step shows
        up, against when the edit was made, is recorded."""
        self._check_completed(run)
        edit_start, edit_end = run.marks["edit-start-s"], run.marks["edit-end-s"]
        steady_start, steady_end = run.steady_window()
        for from_port, to_port in run.directions:
            name = f"{run.label}: {from_port}→{to_port}"
            base = baseline.latency_ms(from_port, to_port)
            old = before.impairment(from_port, to_port).delay_ms
            new = after.impairment(from_port, to_port).delay_ms
            series = [(at, us / 1000) for at, us in run.series(to_port, "avg-latency", steady_start, steady_end)]
            first = [ms for at, ms in series if at <= edit_start - SWITCH_MARGIN_S]
            second = [ms for at, ms in series if at >= edit_end + SWITCH_MARGIN_S]
            for label, values, delay in (("before", first, old), ("after", second, new)):
                self.metrics.check(f"{name} per-second latency {label} the edit",
                                   expected=round(base + delay, 3),
                                   measured=round(median(values), 3) if values else None,
                                   tolerance=latency_tolerance_ms(delay), unit="ms")
            midpoint = base + (old + new) / 2
            step = next((at for at, ms in series if (ms > midpoint) == (new > old)), None)
            self.metrics.check(f"{name} latency steps when the edit is applied (s after Start)",
                               expected=round((edit_start + edit_end) / 2, 1), measured=step,
                               tolerance=round((edit_end - edit_start) / 2 + SWITCH_MARGIN_S, 1),
                               unit="s", enforced=False)

    def check_drain(self, run: WanRun, baseline: WanRun, path: WanPathSpec) -> None:
        """A delay long against the run: the run is still saved, latency
        rises by the delay, and the saved run is honest about its tail:
        `tail-not-settled` is set exactly when frames were still in flight
        (sent, but neither received nor dropped) when it was saved."""
        self._check_completed(run)
        ntg = run.result.ntg
        in_flight = 0
        for from_port, to_port in run.directions:
            delay = path.impairment(from_port, to_port).delay_ms
            name = f"{run.label}: {from_port}→{to_port}"
            added = run.latency_ms(from_port, to_port) - baseline.latency_ms(from_port, to_port)
            self.metrics.check(f"{name} avg latency added", expected=delay, measured=round(added, 3),
                               tolerance=latency_tolerance_ms(delay), unit="ms")
            d = run.direction(from_port, to_port)
            in_flight += d["tx-frames"] - d["rx-frames"] - (run.emulator(from_port, to_port).get("drops") or 0)
        self.metrics.check(f"{run.label}: tail-not-settled set exactly when frames were in flight "
                           f"({in_flight} frames)", expected=in_flight > MIN_FRAME_SLACK,
                           measured=ntg.get("tail-not-settled"))
        longest = max(path.impairment(a, b).delay_ms for a, b in run.directions) / 1000
        self.metrics.at_least(f"{run.label}: tail window covers the delay",
                              minimum=longest, measured=(ntg.get("stages") or {}).get("tail-sec"),
                              unit="s", enforced=False)

    def check_preset(self, run: WanRun, baseline: WanRun, path: WanPathSpec,
                     frame_bytes: int = 1500) -> None:
        """A preset's spec (read_preset), per direction, run below its caps:
        latency rises by its mean delay plus the queueing an NTG burst
        meets at the cap (burst_queue_ms), loss is its random loss, frame
        for frame with the emulator, and the full offered rate arrives.
        Where the preset reorders frames (4G LTE 0.01 %, GEO's uniform
        delay may reorder), the loss checks are recorded, not enforced:
        how the NTG counts late frames is T18b's question, not this one."""
        for from_port, to_port in run.directions:
            imp = path.impairment(from_port, to_port)
            name = f"{run.label}: {from_port}→{to_port}"
            ntg, emu = run.direction(from_port, to_port), run.emulator(from_port, to_port)
            mean = imp.mean_delay_ms
            queueing = burst_queue_ms(imp.bandwidth_mbps, frame_bytes)
            added = run.latency_ms(from_port, to_port) - baseline.latency_ms(from_port, to_port)
            self.metrics.check(f"{name} avg latency added = {_num(mean)} ms delay + "
                               f"{queueing:.1f} ms burst queueing at the cap",
                               expected=round(mean + queueing, 3), measured=round(added, 3),
                               tolerance=max(latency_tolerance_ms(mean + queueing),
                                             JITTER_MEAN_TOLERANCE_SIGMA * imp.delay_sigma_ms), unit="ms")
            exact = not imp.alters_sequence
            self.metrics.check(f"{name} NTG loss %", expected=imp.loss_pct, measured=ntg.get("loss-pct"),
                               tolerance=loss_tolerance_pp(imp.loss_pct, ntg["tx-frames"]), unit="%",
                               enforced=exact)
            wan_drops = (emu.get("wan") or {}).get("drops")
            self.metrics.check(f"{name} NTG frames lost = emulator WAN drops", expected=wan_drops,
                               measured=ntg.get("dropped"), tolerance=frame_tolerance(wan_drops),
                               unit="frames", enforced=exact)
            offered = run.steady_mbps(from_port, "tx-rate")
            received = run.steady_mbps(to_port, "rx-rate")
            if offered and received is not None:
                expected = round(offered * (1 - imp.loss_pct / 100), 3)
                self.metrics.check(f"{name} received rate = offered less loss (below the cap)",
                                   expected=expected, measured=received,
                                   tolerance=max(expected * THROUGHPUT_TOLERANCE_PCT / 100, 0.01),
                                   unit="Mbps", enforced=exact)

    def check_per_stream(self, run: WanRun, baseline: WanRun, routes: Dict[int, WanPathSpec]) -> None:
        """Each stream through its own path (routed), per stream and
        direction: the NTG's per-stream latency and loss show only that
        stream's path, and the emulator carried that stream's frames on
        that path."""
        for flow, path in routes.items():
            for from_port, to_port in run.directions:
                imp = path.impairment(from_port, to_port)
                name = f"{run.label}: stream {flow} {from_port}→{to_port} via {path.name}"
                d = run.flow_direction(flow, from_port, to_port)
                b = baseline.flow_direction(flow, from_port, to_port)
                added = (d["avg-latency"] - b["avg-latency"]) / 1000
                self.metrics.check(f"{name} avg latency added", expected=imp.delay_ms,
                                   measured=round(added, 3), tolerance=latency_tolerance_ms(imp.delay_ms),
                                   unit="ms")
                self.metrics.check(f"{name} NTG loss %", expected=imp.loss_pct, measured=d.get("loss-pct"),
                                   tolerance=loss_tolerance_pp(imp.loss_pct, d["tx-frames"]), unit="%")
                emu = run.emulator_path(path.name, from_port, to_port)
                self.metrics.check(f"{name} emulator frames delivered on this path = stream's frames received",
                                   expected=d["rx-frames"], measured=emu.get("frames"),
                                   tolerance=frame_tolerance(d["rx-frames"]), unit="frames")

    def _check_completed(self, run: WanRun) -> None:
        self.metrics.check(f"{run.label}: run saved as completed", expected="completed",
                           measured=run.result.ntg.get("end-reason"))

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


def _combine(parts: List[dict]) -> dict:
    """Several streams' saved totals for one direction as one: frames
    summed, latencies weighted by frames received, extremes kept."""
    tx = sum(d.get("tx-frames") or 0 for d in parts)
    rx = sum(d.get("rx-frames") or 0 for d in parts)
    out = {"from-port": parts[0]["from-port"], "to-port": parts[0]["to-port"],
           "tx-frames": tx, "rx-frames": rx, "dropped": sum(d.get("dropped") or 0 for d in parts),
           "loss-pct": round(100 * (tx - rx) / tx, 4) if tx else None}
    for stat in ("avg-latency", "avg-jitter"):
        weighted = [(d[stat], d.get("rx-frames") or 0) for d in parts if stat in d]
        if weighted and rx:
            out[stat] = sum(v * w for v, w in weighted) / rx
    for stat, pick in (("min-latency", min), ("max-latency", max)):
        values = [d[stat] for d in parts if stat in d]
        if values:
            out[stat] = pick(values)
    return out


def _sum(flows: List[dict]) -> dict:
    """Several paths' counter growth for one direction, added up."""
    if not flows:
        return {}
    total = flows[0]
    for flow in flows[1:]:
        total = _add(total, flow)
    return total


def _add(a, b):
    if isinstance(a, dict):
        return {k: (v if k in _ID_FIELDS else _add(v, (b or {}).get(k))) for k, v in a.items()}
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return a + b
    return a


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

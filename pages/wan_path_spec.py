"""The config block for a WAN emulator path, the emulator's counterpart of
TestbedSpec. One `Impairment` per direction; WanEmulatorPage turns a
WanPathSpec into form input, and the stored path (WanApi.engine()) uses the
same slash-separated names as JSON keys, so a spec can be checked against
what the box actually saved.

Directions: the path's "source" side is the engine's first port (port-a),
so source-to-destination is emulator port 3 -> 4 on Engine 2, which is NTG
Port 3 -> 4. Each direction enters the WAN through its sender's outbound
access link (source/outbound for a-to-b), which is where a bandwidth cap
and its queue sit; the emulator's stats call that link the direction's
"inflow".

    WanPathSpec("t15-asym", a_to_b=Impairment(delay_ms=10), b_to_a=Impairment(delay_ms=80))
    WanPathSpec("t17-cap", a_to_b=Impairment(bandwidth_mbps=100))
    WanPathSpec("t18-jitter", a_to_b=Impairment(delay_ms=20, jitter_ms=5))
    WanPathSpec("t19-outage", a_to_b=Impairment(outage_s=2, outage_every_s=10))

Field names come from the 2026-10-11 form crawl (docs/wan-emulator-reference.md)
and the stored-path JSON, whose keys mirror them. The fields added for
T18-T21 (normal delay, duplication, reordering, outage) haven't been typed
into the real form yet: tests/t0_library/test_t0_wan_library.py round-trips
every one of them, so run it before trusting a hardware result.

WanPathSpec.from_saved() goes the other way, from a stored path to a spec.
T20 uses it to turn a built-in preset into a spec the bench can check.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

A_TO_B = "source-to-destination"
B_TO_A = "destination-to-source"
# A new path's access links default to 128 Kbps, which would throttle any
# NTG run to nothing; a direction without a cap is opened up to this.
WIDE_OPEN_GBPS = 10
_ACCESS_LINK = {A_TO_B: "source/outbound", B_TO_A: "destination/outbound"}
_MBPS_PER = {"Gbps": 1000, "Mbps": 1, "Kbps": 0.001}


class NotModelled(ValueError):
    """A stored path uses an emulator setting Impairment can't describe
    (uniform delay, burst loss, background utilisation, ...), so the bench
    couldn't say what the NTG should measure."""


@dataclass(frozen=True)
class Impairment:
    """What the emulator does to one direction. Extend here as tests need
    it; each field maps to its form fields in fields()."""
    delay_ms: float = 0                    # one-way delay; the mean when jitter_ms is set,
                                           # the minimum when delay_max_ms is
    jitter_ms: float = 0                   # normal-distribution σ around delay_ms
    delay_max_ms: float = 0                # uniform delay between delay_ms and this
    allow_reordering: bool = False         # variable delay may reorder frames (else skewed to keep order)
    loss_pct: float = 0                    # random loss, % of frames
    bandwidth_mbps: Optional[float] = None  # access-link cap; None = wide open
    duplicate_pct: float = 0               # % of frames sent twice
    reorder_pct: float = 0                 # % of frames held back...
    reorder_offset: int = 3                # ...by this many frames
    outage_s: float = 0                    # periodic outage: down this long...
    outage_every_s: float = 0              # ...every this many seconds (start to start)

    def __post_init__(self):
        # The emulator refuses a normal distribution whose mean is under 3σ
        # (it would need negative delays).
        assert not self.jitter_ms or self.delay_ms >= 3 * self.jitter_ms, (
            f"jitter needs delay_ms >= 3 × jitter_ms, got {self.delay_ms} / {self.jitter_ms}"
        )
        assert bool(self.outage_s) == bool(self.outage_every_s), (
            "give both outage_s and outage_every_s, or neither"
        )
        assert not (self.jitter_ms and self.delay_max_ms), "normal or uniform delay, not both"
        assert not self.delay_max_ms or self.delay_max_ms > self.delay_ms, (
            "uniform delay needs delay_max_ms > delay_ms"
        )
        assert not self.allow_reordering or self.variable_delay, (
            "Allow Reordering only exists for variable (normal/uniform) delay"
        )

    @property
    def variable_delay(self) -> bool:
        return bool(self.jitter_ms or self.delay_max_ms)

    @property
    def mean_delay_ms(self) -> float:
        """The average delay this direction adds."""
        return (self.delay_ms + self.delay_max_ms) / 2 if self.delay_max_ms else self.delay_ms

    @property
    def delay_sigma_ms(self) -> float:
        """The delay's standard deviation (uniform: width / √12)."""
        if self.delay_max_ms:
            return (self.delay_max_ms - self.delay_ms) / 12 ** 0.5
        return self.jitter_ms

    def fields(self, direction: str, wide_open_gbps: float = WIDE_OPEN_GBPS) -> Dict[str, str]:
        link = f"{_ACCESS_LINK[direction]}/bandwidth"
        # Metric before rate: the rate is read in the selected unit.
        if self.bandwidth_mbps:
            values = {f"{link}/metric": "Mbps", f"{link}/rate": _num(self.bandwidth_mbps)}
        else:
            values = {f"{link}/metric": "Gbps", f"{link}/rate": _num(wide_open_gbps)}
        wan = f"wan/{direction}"
        # Each method select must come first: it reveals its value input.
        if self.jitter_ms:
            values[f"{wan}/delay/method"] = "normal"
            values[f"{wan}/delay/normal/mean"] = _num(self.delay_ms)
            values[f"{wan}/delay/normal/standard-deviation"] = _num(self.jitter_ms)
        elif self.delay_max_ms:
            values[f"{wan}/delay/method"] = "uniform"
            values[f"{wan}/delay/uniform/minimum"] = _num(self.delay_ms)
            values[f"{wan}/delay/uniform/maximum"] = _num(self.delay_max_ms)
        elif self.delay_ms:
            values[f"{wan}/delay/method"] = "constant"
            values[f"{wan}/delay/constant/latency"] = _num(self.delay_ms)
        if self.variable_delay:
            # A checkbox. Off (the default), the emulator skews delays to
            # keep frames in order, which is what a real path does.
            values[f"{wan}/delay/reordering"] = _num(self.allow_reordering)
        if self.loss_pct:
            values[f"{wan}/loss/method"] = "random"
            values[f"{wan}/loss/random/rate"] = _num(self.loss_pct)
        if self.outage_s:
            values[f"{wan}/outage/method"] = "periodic"
            values[f"{wan}/outage/duration"] = _num(self.outage_s)
            values[f"{wan}/outage/interval"] = _num(self.outage_every_s)
        if self.reorder_pct:
            values[f"{wan}/reordering/method"] = "on"
            values[f"{wan}/reordering/probability"] = _num(self.reorder_pct)
            values[f"{wan}/reordering/offset"] = _num(self.reorder_offset)
        if self.duplicate_pct:
            values[f"{wan}/duplication/method"] = "on"
            values[f"{wan}/duplication/probability"] = _num(self.duplicate_pct)
        return values

    def describe(self) -> dict:
        described = {}
        if self.jitter_ms:
            described["delay"] = f"normal, mean {_num(self.delay_ms)} ms, σ {_num(self.jitter_ms)} ms"
        elif self.delay_max_ms:
            described["delay"] = f"uniform {_num(self.delay_ms)}-{_num(self.delay_max_ms)} ms"
        elif self.delay_ms:
            described["delay"] = f"constant {_num(self.delay_ms)} ms"
        if self.allow_reordering:
            described["delay"] += ", may reorder"
        if self.loss_pct:
            described["loss"] = f"random {_num(self.loss_pct)} %"
        if self.bandwidth_mbps:
            described["bandwidth"] = f"{_num(self.bandwidth_mbps)} Mbps"
        if self.outage_s:
            described["outage"] = f"{_num(self.outage_s)} s every {_num(self.outage_every_s)} s"
        if self.reorder_pct:
            described["reordering"] = f"{_num(self.reorder_pct)} % by {self.reorder_offset} frames"
        if self.duplicate_pct:
            described["duplication"] = f"{_num(self.duplicate_pct)} %"
        return described

    def loses_frames(self, offered_mbps: Optional[float]) -> bool:
        """True when this direction drops frames by design for traffic
        offered at `offered_mbps`: random loss, an outage, or a cap below
        the offer."""
        capped = bool(self.bandwidth_mbps and offered_mbps and self.bandwidth_mbps < offered_mbps)
        return bool(self.loss_pct or self.outage_s) or capped

    @property
    def alters_sequence(self) -> bool:
        """Frames arrive twice or out of order. How the NTG counts that is
        exactly what T18b finds out, so its default verdict means nothing."""
        return bool(self.duplicate_pct or self.reorder_pct or self.allow_reordering)

    @classmethod
    def from_saved(cls, wan: dict, outbound: dict, inbound: dict = None,
                   wide_open_gbps: float = WIDE_OPEN_GBPS) -> "Impairment":
        """The Impairment a stored direction amounts to. `wan` is the path's
        wan/<direction> block, `outbound` the sender's outbound access link
        and `inbound` the receiver's inbound one. Presets switch inbound
        links on (4G LTE does, 2026-10-19): traffic then crosses both, so
        the direction's cap is the tighter of the two. Raises NotModelled
        for anything this class can't describe."""
        unsupported = []
        kw = {}
        delay = wan.get("delay") or {}
        method = delay.get("method", "off")
        if method == "constant":
            kw["delay_ms"] = float(delay["constant"]["latency"])
        elif method in ("normal", "uniform"):
            if method == "normal":
                kw["delay_ms"] = float(delay["normal"]["mean"])
                kw["jitter_ms"] = float(delay["normal"]["standard-deviation"])
            else:
                kw["delay_ms"] = float(delay["uniform"]["minimum"])
                kw["delay_max_ms"] = float(delay["uniform"]["maximum"])
            kw["allow_reordering"] = bool(delay.get("reordering"))
        elif method != "off":
            unsupported.append(f"delay method {method!r}")
        loss = wan.get("loss") or {}
        if loss.get("method") == "random":
            kw["loss_pct"] = float(loss["random"]["rate"])
        elif loss.get("method", "off") != "off":
            unsupported.append(f"loss method {loss['method']!r}")
        outage = wan.get("outage") or {}
        if outage.get("method") == "periodic":
            kw["outage_s"] = float(outage["duration"])
            kw["outage_every_s"] = float(outage["interval"])
        reordering = wan.get("reordering") or {}
        if reordering.get("method") == "on":
            kw["reorder_pct"] = float(reordering["probability"])
            kw["reorder_offset"] = int(reordering["offset"])
        duplication = wan.get("duplication") or {}
        if duplication.get("method") == "on":
            kw["duplicate_pct"] = float(duplication["probability"])
        for name in ("corruption", "mangle"):
            if (wan.get(name) or {}).get("method", "off") != "off":
                unsupported.append(name)

        links = [outbound] + ([inbound] if inbound and inbound.get("enabled") else [])
        caps = []
        for link in links:
            bandwidth = link.get("bandwidth") or {}
            caps.append(float(bandwidth.get("rate", 0)) * _MBPS_PER[bandwidth.get("metric", "Mbps")])
            if link.get("mode", "single") != "single":
                unsupported.append(f"link mode {link['mode']!r}")
            if (link.get("utilization") or {}).get("method", "off") != "off":
                unsupported.append("background utilisation")
            if (link.get("mtu") or {}).get("enabled"):
                unsupported.append("MTU limit")
            # Both change what a cap delivers (queue depth, bytes charged per frame).
            if (link.get("queue") or {}).get("algorithm", "auto") != "auto":
                unsupported.append(f"queue {link['queue']['algorithm']!r}")
            if (link.get("frame") or {}).get("overhead", "header-fcs") != "header-fcs":
                unsupported.append(f"frame overhead {link['frame']['overhead']!r}")
        if min(caps) < wide_open_gbps * 1000:
            kw["bandwidth_mbps"] = round(min(caps), 6)
        if unsupported:
            raise NotModelled(", ".join(unsupported))
        return cls(**kw)


@dataclass(frozen=True)
class WanPathSpec:
    name: str
    a_to_b: Impairment = field(default_factory=Impairment)
    b_to_a: Optional[Impairment] = None   # None = same as a_to_b
    access_gbps: float = WIDE_OPEN_GBPS

    @property
    def reverse(self) -> Impairment:
        return self.a_to_b if self.b_to_a is None else self.b_to_a

    def impairment(self, from_port: int, to_port: int) -> Impairment:
        """The impairment on NTG traffic from `from_port` to `to_port`
        (Port 3 -> 4 is a-to-b)."""
        return self.a_to_b if from_port < to_port else self.reverse

    def form_fields(self) -> Dict[str, str]:
        """{form control name: value}, in the order they must be set."""
        return {**self.a_to_b.fields(A_TO_B, self.access_gbps),
                **self.reverse.fields(B_TO_A, self.access_gbps)}

    def describe(self, engine: int) -> dict:
        """For the summary sheet's `impairment` block."""
        return {"engine": engine, "path": self.name,
                "a-to-b": self.a_to_b.describe(), "b-to-a": self.reverse.describe()}

    @property
    def min_cap_mbps(self) -> Optional[float]:
        """The tighter direction's bandwidth cap, if any."""
        caps = [i.bandwidth_mbps for i in (self.a_to_b, self.reverse) if i.bandwidth_mbps]
        return min(caps) if caps else None

    @classmethod
    def from_saved(cls, saved_path: dict, name: str = None) -> "WanPathSpec":
        """The spec a stored path (one entry of WanApi.engine(i)["path"])
        amounts to, e.g. one a built-in preset filled in. Raises
        NotModelled, naming each setting, when it uses anything Impairment
        can't describe. Inbound access links are off on every path the
        suite makes; a preset's are folded into its caps (the spec then
        types the tighter cap on the outbound link alone)."""
        wan = saved_path.get("wan") or {}
        source, destination = saved_path["source"], saved_path["destination"]
        a_to_b = Impairment.from_saved(wan.get(A_TO_B) or {}, source["outbound"],
                                       destination.get("inbound"))
        b_to_a = Impairment.from_saved(wan.get(B_TO_A) or {}, destination["outbound"],
                                       source.get("inbound"))
        return cls(name or saved_path["label"], a_to_b, None if b_to_a == a_to_b else b_to_a)

    def mismatches(self, saved_path: dict) -> Dict[str, tuple]:
        """{field: (wanted, saved)} for each form field the box didn't store
        as asked. `saved_path` is one entry of WanApi.engine(i)["path"]."""
        wrong = {}
        for key, wanted in self.form_fields().items():
            saved = saved_path
            for part in key.split("/"):
                saved = (saved or {}).get(part) if isinstance(saved, dict) else None
            if _num(saved) != wanted:
                wrong[key] = (wanted, saved)
        return wrong


@dataclass(frozen=True)
class EndpointSpec:
    """An emulator endpoint: traffic of host `ipaddrs` on emulator `port`
    (3 or 4 on Engine 2, i.e. NTG Port 3 or 4) that matches `protocol`
    goes to path `path`. Everything else follows the ports' Default
    Action. T21 uses one per (port, protocol) to give each NTG stream its
    own path. The emulator needs an address: without one, Create Endpoint
    silently saves nothing (seen 2026-10-19)."""
    label: str
    port: int
    protocol: str    # "udp" / "tcp" (the form's option values)
    path: str
    ipaddrs: str     # the NTG port's own IP (an address, range or subnet)
    # With the transport ports left empty the protocol doesn't classify:
    # on 2026-10-19 a UDP endpoint caught the TCP stream too (first match
    # by address). A full range makes the protocol count.
    transports: str = "1-65535"

    def form_fields(self) -> Dict[str, str]:
        """{form control name: value}; the action select takes the path's label."""
        return {"label": self.label, "port": str(self.port), "ipaddrs": self.ipaddrs,
                "protocol": self.protocol, "transports": self.transports}


def _num(value) -> str:
    """10 -> "10", 10.0 -> "10", 2.5 -> "2.5", "Gbps" -> "Gbps", True -> "true"."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)

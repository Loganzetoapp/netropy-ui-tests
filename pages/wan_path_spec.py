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
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

A_TO_B = "source-to-destination"
B_TO_A = "destination-to-source"
# A new path's access links default to 128 Kbps, which would throttle any
# NTG run to nothing; a direction without a cap is opened up to this.
WIDE_OPEN_GBPS = 10
_ACCESS_LINK = {A_TO_B: "source/outbound", B_TO_A: "destination/outbound"}


@dataclass(frozen=True)
class Impairment:
    """What the emulator does to one direction. Extend here as tests need
    it; each field maps to its form fields in fields()."""
    delay_ms: float = 0                    # constant one-way delay
    loss_pct: float = 0                    # random loss, % of frames
    bandwidth_mbps: Optional[float] = None  # access-link cap; None = wide open

    def fields(self, direction: str, wide_open_gbps: float = WIDE_OPEN_GBPS) -> Dict[str, str]:
        link = f"{_ACCESS_LINK[direction]}/bandwidth"
        # Metric before rate: the rate is read in the selected unit.
        if self.bandwidth_mbps:
            values = {f"{link}/metric": "Mbps", f"{link}/rate": _num(self.bandwidth_mbps)}
        else:
            values = {f"{link}/metric": "Gbps", f"{link}/rate": _num(wide_open_gbps)}
        wan = f"wan/{direction}"
        # Each method select must come first: it reveals its value input.
        if self.delay_ms:
            values[f"{wan}/delay/method"] = "constant"
            values[f"{wan}/delay/constant/latency"] = _num(self.delay_ms)
        if self.loss_pct:
            values[f"{wan}/loss/method"] = "random"
            values[f"{wan}/loss/random/rate"] = _num(self.loss_pct)
        return values

    def describe(self) -> dict:
        described = {}
        if self.delay_ms:
            described["delay"] = f"constant {_num(self.delay_ms)} ms"
        if self.loss_pct:
            described["loss"] = f"random {_num(self.loss_pct)} %"
        if self.bandwidth_mbps:
            described["bandwidth"] = f"{_num(self.bandwidth_mbps)} Mbps"
        return described

    def loses_frames(self, offered_mbps: Optional[float]) -> bool:
        """True when this direction drops frames by design for traffic
        offered at `offered_mbps`: random loss, or a cap below the offer."""
        capped = bool(self.bandwidth_mbps and offered_mbps and self.bandwidth_mbps < offered_mbps)
        return bool(self.loss_pct) or capped


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


def _num(value) -> str:
    """10 -> "10", 10.0 -> "10", 2.5 -> "2.5", "Gbps" -> "Gbps"."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)

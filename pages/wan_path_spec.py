"""The config block for a WAN emulator path, the emulator's counterpart of
TestbedSpec. One `Impairment` per direction; WanEmulatorPage turns a
WanPathSpec into form input, and the stored path (WanApi.engine()) uses the
same slash-separated names as JSON keys, so a spec can be checked against
what the box actually saved.

Directions: the path's "source" side is the engine's first port (port-a),
so source-to-destination is emulator port 3 -> 4 on Engine 2, which is NTG
Port 3 -> 4.

    WanPathSpec("t15-asym", a_to_b=Impairment(delay_ms=10), b_to_a=Impairment(delay_ms=80))
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

A_TO_B = "source-to-destination"
B_TO_A = "destination-to-source"
# A new path's access links default to 128 Kbps, which would throttle any
# NTG run to nothing; impairment tests open them up to the port speed.
WIDE_OPEN_GBPS = 10
_ACCESS_LINKS = ("source/outbound", "destination/outbound")


@dataclass(frozen=True)
class Impairment:
    """What the emulator does to one direction. Extend here (loss, jitter,
    ...) as tests need it; each field maps to its form fields in fields()."""
    delay_ms: float = 0  # constant one-way delay

    def fields(self, direction: str) -> Dict[str, str]:
        if not self.delay_ms:
            return {}
        prefix = f"wan/{direction}/delay"
        # The method select must come first: it reveals the latency input.
        return {f"{prefix}/method": "constant", f"{prefix}/constant/latency": _num(self.delay_ms)}

    def describe(self) -> dict:
        return {"delay": f"constant {_num(self.delay_ms)} ms"} if self.delay_ms else {}


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
        values = {}
        for link in _ACCESS_LINKS:
            values[f"{link}/bandwidth/metric"] = "Gbps"
            values[f"{link}/bandwidth/rate"] = _num(self.access_gbps)
        values.update(self.a_to_b.fields(A_TO_B))
        values.update(self.reverse.fields(B_TO_A))
        return values

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

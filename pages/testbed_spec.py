"""The "config block" a traffic test declares: ports, addressing, streams
and how long to run. TrafficEngine turns it into editor clicks."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PortSpec:
    rate: Optional[float] = None          # line rate, in `unit`; None = leave the default
    unit: str = "Gbps"                    # Gbps / Mbps / Kbps
    direction: str = "bidirectional"      # bidirectional / tx only / rx only
    peer: Optional[int] = None            # None = the editor's auto-peering
    ip: Optional[str] = None              # source IP; None = the editor's default
    cidr: Optional[int] = None            # 25..32 on 5.0.9
    dst_ip: Optional[str] = None          # None = peer's source IP when both ports have one
    gateway_ip: Optional[str] = None      # next hop = gateway instead of dest MAC

    @property
    def rate_mbps(self) -> Optional[float]:
        if self.rate is None:
            return None
        return float(self.rate) * {"Gbps": 1000, "Mbps": 1, "Kbps": 0.001}[self.unit]


@dataclass
class StreamSpec:
    protocol: str                          # Add Stream list label: UDP, TCP, ICMP, DNS, NTP, ARP, ...
    frame_size: Optional[int] = None
    quantity: int = 1
    name: Optional[str] = None


@dataclass
class TestbedSpec:
    __test__ = False  # not a pytest test class

    ports: Dict[int, PortSpec]
    streams: List[StreamSpec]
    duration_s: Optional[int] = None                 # flat run (0 / N / 0 ramp)
    ramp: Optional[Tuple[int, int, int]] = None      # (up, hold, down) seconds
    frame_size: Optional[int] = None                 # "apply to all"
    expect_traffic: bool = True                      # enforce frames sent/received > 0
    expect_loss: bool = False                        # frames are lost on purpose (impaired WAN)

    def __post_init__(self):
        assert self.duration_s or self.ramp, (
            "Give duration_s or ramp: a testbed with neither runs until someone presses Stop."
        )

    @property
    def run_seconds(self) -> int:
        return sum(self.ramp) if self.ramp else self.duration_s

    @property
    def port_numbers(self) -> List[int]:
        return sorted(self.ports)

    def destination_for(self, port: int) -> Optional[str]:
        spec = self.ports[port]
        if spec.dst_ip:
            return spec.dst_ip
        peer = spec.peer or next((p for p in self.ports if p != port), None)
        return self.ports[peer].ip if peer is not None else None

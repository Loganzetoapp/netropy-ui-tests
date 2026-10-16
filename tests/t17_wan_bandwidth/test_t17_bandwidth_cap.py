"""T17a: bandwidth cap. 100 Mbps each way against 500 Mbps offered: the
NTG must receive the cap, the other ~80 % is tail-dropped at the
emulator's queue (the NTG's lost frames = the emulator's queue drops),
and the full queue shows up as added latency.

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

PATH = WanPathSpec("t17-cap-100", a_to_b=Impairment(bandwidth_mbps=100))


@pytest.mark.stateful
def test_t17_bandwidth_cap_limits_throughput(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)
    capped = wan_bench.impaired(TESTBED, SPEC, PATH)
    wan_bench.check_bandwidth(capped, baseline, PATH)
    wan_bench.assert_ok()

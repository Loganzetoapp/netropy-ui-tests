"""T17b: cap with headroom. 600 Mbps each way against 500 Mbps offered:
the shaper must be invisible, with nothing lost, the full offered rate
received, and no added latency. Catches a shaper that drops or queues
traffic it has room for.

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

PATH = WanPathSpec("t17-cap-600", a_to_b=Impairment(bandwidth_mbps=600))


@pytest.mark.stateful
def test_t17_cap_with_headroom_is_invisible(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)
    capped = wan_bench.impaired(TESTBED, SPEC, PATH)
    wan_bench.check_bandwidth(capped, baseline, PATH)
    wan_bench.assert_ok()

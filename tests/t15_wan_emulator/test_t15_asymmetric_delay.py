"""T15c: asymmetric delay. 10 ms Port 3 -> 4, 80 ms Port 4 -> 3. Real
links are often asymmetric; the NTG must report each direction's own
latency, not an average of both. Also pins down the direction mapping:
the emulator's source-to-destination is NTG Port 3 -> 4.

Stateful: real traffic on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

PATH = WanPathSpec("t15-asym", a_to_b=Impairment(delay_ms=10), b_to_a=Impairment(delay_ms=80))


@pytest.mark.stateful
def test_t15_asymmetric_delay_reported_per_direction(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)
    delayed = wan_bench.impaired(TESTBED, SPEC, PATH)
    wan_bench.check_delay(delayed, baseline, PATH)
    wan_bench.assert_ok()

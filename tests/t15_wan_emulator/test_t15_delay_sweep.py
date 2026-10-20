"""T15b: delay sweep. The same constant delay check across three decades
(1 to 500 ms) catches unit slips (µs vs ms) and any non-linearity in how
the NTG measures latency or the emulator applies it. At 500 ms each
direction holds about 30 MB in flight, which also exercises the
emulator's buffering.

Stateful: one run per setting on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED


@pytest.mark.stateful
@pytest.mark.parametrize("delay_ms", [1, 10, 100, 500])
def test_t15_delay_sweep_latency_tracks_setting(wan_bench, delay_ms):
    path = WanPathSpec(f"t15-sweep-{delay_ms}", a_to_b=Impairment(delay_ms=delay_ms))
    baseline = wan_bench.baseline(TESTBED, SPEC)
    delayed = wan_bench.impaired(TESTBED, SPEC, path)
    wan_bench.check_delay(delayed, baseline, path)
    wan_bench.assert_ok()

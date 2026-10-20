"""T15a: delay only. 50 ms constant each way; the NTG's one-way latency
in both directions must rise by 50 ms, and the run must still pass with
the emulator dropping nothing.

From the 2026-09-30 meeting: drive the WAN emulator together with the
traffic engine, delay first. Stateful: real traffic on Ports 3/4 and a
reconfigured Engine 2 on the shared emulator (restored afterwards)."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

PATH = WanPathSpec("t15-delay", a_to_b=Impairment(delay_ms=50))


@pytest.mark.stateful
def test_t15_delay_only_adds_expected_latency(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)
    delayed = wan_bench.impaired(TESTBED, SPEC, PATH)
    wan_bench.check_delay(delayed, baseline, PATH)
    wan_bench.assert_ok()

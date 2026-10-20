"""T19c: long delay vs the drain window. 2 s each way on a 10 s run: the
run must still be saved (not lost), latency must rise by 2 s, and the
saved run must be honest about its tail: `tail-not-settled` set exactly
when frames were still in flight when it was saved. Overlaps the NTG's
lost-run finding (netropy-ui-findings.md).

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SLOW_SPEC, TESTBED

PATH = WanPathSpec("t19-drain", a_to_b=Impairment(delay_ms=2000))


@pytest.mark.stateful
def test_t19_long_delay_run_saved_with_honest_tail(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SLOW_SPEC)
    run = wan_bench.impaired(TESTBED, SLOW_SPEC, PATH)
    wan_bench.check_drain(run, baseline, PATH)
    wan_bench.assert_ok()

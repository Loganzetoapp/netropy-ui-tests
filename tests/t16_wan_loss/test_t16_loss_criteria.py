"""T16b: loss vs the NTG's pass criteria. One run with 2 % loss each way,
then re-judged through its "Edit pass criteria" popover: Max loss 1 %
must turn it FAIL and Max loss 5 % must turn it PASS, on screen and in
the Controller. The first test that makes the NTG's own verdict mean
something: without criteria it is a loss-based default nobody documented.

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

PATH = WanPathSpec("t16-criteria", a_to_b=Impairment(loss_pct=2))


@pytest.mark.stateful
def test_t16_loss_criteria_decide_the_verdict(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)
    lossy = wan_bench.impaired(TESTBED, SPEC, PATH)
    wan_bench.check_loss(lossy, baseline, PATH)
    wan_bench.check_verdict(lossy, TESTBED, max_loss_pct=1)
    wan_bench.check_verdict(lossy, TESTBED, max_loss_pct=5)
    wan_bench.assert_ok()

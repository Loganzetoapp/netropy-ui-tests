"""T19b: change mid-run. Start at 10 ms each way, then edit the path to
100 ms (Apply Changes) 20 s into a 44 s run: the NTG's per-second latency
must sit at 10 ms before the edit and 100 ms after it, and the run must
still be saved. When the step shows up is recorded against when the edit
was made.

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import LONG_SPEC, TESTBED

BEFORE = WanPathSpec("t19-step", a_to_b=Impairment(delay_ms=10))
AFTER = WanPathSpec("t19-step", a_to_b=Impairment(delay_ms=100))


@pytest.mark.stateful
def test_t19_latency_steps_when_path_changes_mid_run(wan_bench):
    baseline = wan_bench.baseline(TESTBED, LONG_SPEC)
    run = wan_bench.impaired_with_change(TESTBED, LONG_SPEC, BEFORE, AFTER, after_s=20)
    wan_bench.check_change(run, baseline, BEFORE, AFTER)
    wan_bench.assert_ok()

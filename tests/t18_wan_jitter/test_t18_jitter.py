"""T18a: jitter. Normal-distribution delay, mean 20 ms and σ 5 ms each
way: the NTG's average latency must rise by the mean, its jitter must
rise, and no frame may arrive later than mean + 6σ. The emulator keeps
frames in order, so how far jitter rises is recorded against the
independent-delay figure until we know which definition the NTG uses.

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

PATH = WanPathSpec("t18-jitter", a_to_b=Impairment(delay_ms=20, jitter_ms=5))


@pytest.mark.stateful
def test_t18_jitter_measured_by_the_ntg(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)
    jittery = wan_bench.impaired(TESTBED, SPEC, PATH)
    wan_bench.check_jitter(jittery, baseline, PATH)
    wan_bench.assert_ok()

"""T19a: outage mid-run. A 2 s outage every 10 s each way, across a 40 s
hold: the run must still be saved, the NTG's per-second receive rate must
go dark during the outages, and every frame it lost must be one the
emulator dropped. Also the crash/bad-state check: a unit that loses the
run here is a system failure.

Stateful: one run on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import LONG_SPEC, TESTBED

PATH = WanPathSpec("t19-outage", a_to_b=Impairment(outage_s=2, outage_every_s=10))


@pytest.mark.stateful
def test_t19_outage_shows_as_gaps_and_run_survives(wan_bench):
    wan_bench.baseline(TESTBED, LONG_SPEC)
    run = wan_bench.impaired(TESTBED, LONG_SPEC, PATH)
    wan_bench.check_outage(run, PATH)
    wan_bench.assert_ok()

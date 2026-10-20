"""T16a: random loss. 1 % and 5 % each way; the NTG's loss % must match
the setting, and every frame it reports lost must be one the emulator
dropped (the two boxes count independently). Loss alone must not move
latency.

Stateful: one run per setting on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED


@pytest.mark.stateful
@pytest.mark.parametrize("loss_pct", [1, 5])
def test_t16_random_loss_counted_by_both_boxes(wan_bench, loss_pct):
    path = WanPathSpec(f"t16-loss-{loss_pct}", a_to_b=Impairment(loss_pct=loss_pct))
    baseline = wan_bench.baseline(TESTBED, SPEC)
    lossy = wan_bench.impaired(TESTBED, SPEC, path)
    wan_bench.check_loss(lossy, baseline, path)
    wan_bench.assert_ok()

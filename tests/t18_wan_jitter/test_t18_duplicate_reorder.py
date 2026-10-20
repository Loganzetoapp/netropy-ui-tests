"""T18b: duplication and reordering, 1 % each way, one at a time so a
miscount points at its cause. Neither loses a frame, so the NTG must not
report negative loss or receive more than it sent plus the emulator's
duplicates. How it counts duplicates and late frames is recorded: the
plan flags this as a likely bug area.

Stateful: one run per case on Ports 3/4 through Engine 2."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import SPEC, TESTBED

CASES = {
    "duplicate": WanPathSpec("t18-dup-1", a_to_b=Impairment(duplicate_pct=1)),
    "reorder": WanPathSpec("t18-reorder-1", a_to_b=Impairment(reorder_pct=1)),
}


@pytest.mark.stateful
@pytest.mark.parametrize("case", list(CASES))
def test_t18_duplicates_and_reorders_never_miscounted(wan_bench, case):
    path = CASES[case]
    wan_bench.baseline(TESTBED, SPEC)
    run = wan_bench.impaired(TESTBED, SPEC, path)
    wan_bench.check_sequence(run, path)
    wan_bench.assert_ok()

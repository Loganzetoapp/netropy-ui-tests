"""T21: per-stream paths. Endpoints send the UDP stream through 2 % loss
and the TCP stream through 30 ms of delay, in one run: each stream's
NTG stats must show only its own path (UDP loses frames but keeps its
latency; TCP is delayed but loses nothing), and the emulator must have
carried each stream on its path.

Stateful: one run on Ports 3/4 through Engine 2 (endpoints, not Default
Actions)."""
import pytest

from pages.wan_path_spec import Impairment, WanPathSpec
from tests.t15_wan_emulator.specs import TESTBED, TWO_STREAM_SPEC

ROUTES = {
    0: WanPathSpec("t21-udp-loss", a_to_b=Impairment(loss_pct=2)),
    1: WanPathSpec("t21-tcp-delay", a_to_b=Impairment(delay_ms=30)),
}


@pytest.mark.stateful
def test_t21_each_stream_shows_only_its_own_path(wan_bench):
    baseline = wan_bench.baseline(TESTBED, TWO_STREAM_SPEC)
    run = wan_bench.routed(TESTBED, TWO_STREAM_SPEC, ROUTES)
    wan_bench.check_per_stream(run, baseline, ROUTES)
    wan_bench.assert_ok()

"""T20: the emulator's built-in presets as a golden set (LTE, GEO
satellite, Wi-Fi 802.11n). Each preset is read back as a spec
(WanBench.read_preset), then run at half its tightest cap: the NTG must
measure its delay (plus the queueing its 32-frame bursts meet at the
cap) and loss, frame for frame with the emulator. A preset
using a setting the library can't describe yet fails, naming it.

Stateful: one baseline and one impaired run per preset on Ports 3/4."""
import pytest

from tests.t15_wan_emulator.specs import TESTBED, bench_spec, preset_rate_mbps

# The preset menu's own item names (mapped 2026-10-19).
PRESETS = {
    "lte": ("Cellular", "4G LTE"),
    "geo": ("Satellite", "GEO"),
    "wifi-n": ("Wi-Fi", "802.11n"),
}


@pytest.mark.stateful
@pytest.mark.parametrize("preset", list(PRESETS))
def test_t20_preset_measured_within_tolerance(wan_bench, preset):
    group, item = PRESETS[preset]
    path = wan_bench.read_preset(group, item, f"t20-{preset}")
    spec = bench_spec(rate_mbps=preset_rate_mbps(path))
    baseline = wan_bench.baseline(TESTBED, spec)
    run = wan_bench.impaired(TESTBED, spec, path)
    wan_bench.check_preset(run, baseline, path, frame_bytes=spec.frame_size)
    wan_bench.assert_ok()

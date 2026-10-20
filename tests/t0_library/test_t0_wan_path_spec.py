"""T0: WanPathSpec and Impairment on their own, no hardware: which form
fields each impairment types, the emulator's own limits, and reading a
stored path back into a spec (WanPathSpec.from_saved, used by T20)."""
import pytest

from pages.wan_bench import burst_queue_ms, loss_tolerance_pp
from pages.wan_path_spec import A_TO_B, B_TO_A, Impairment, NotModelled, WanPathSpec

EVERYTHING = WanPathSpec(
    "t0-lib-all",
    a_to_b=Impairment(delay_ms=20, jitter_ms=5, loss_pct=1.5, bandwidth_mbps=100, duplicate_pct=1,
                      reorder_pct=2, reorder_offset=4, outage_s=2, outage_every_s=10),
    b_to_a=Impairment(delay_ms=80, loss_pct=0.25, bandwidth_mbps=250),
)


def _stored(spec: WanPathSpec) -> dict:
    """A stored path as the emulator's API returns it: every block present,
    off unless the form set it (the shape seen 2026-10-12), with the
    spec's form fields written in."""
    def direction():
        return {"delay": {"method": "off", "reordering": False, "constant": {"latency": 0},
                          "normal": {"mean": 0, "standard-deviation": 0},
                          "uniform": {"minimum": 0, "maximum": 0}},
                "loss": {"method": "off", "random": {"rate": 0}},
                "outage": {"method": "off", "duration": "1", "interval": "60"},
                "corruption": {"method": "off"},
                "reordering": {"method": "off", "probability": 0, "offset": "1", "timeout": 10000},
                "duplication": {"method": "off", "probability": 0},
                "mangle": {"method": "off"}}

    def link():
        return {"mode": "single", "enabled": True, "bandwidth": {"rate": 128, "metric": "Kbps"},
                "queue": {"algorithm": "auto"}, "mtu": {"enabled": False},
                "frame": {"overhead": "header-fcs"}}

    saved = {"label": spec.name, "wan": {A_TO_B: direction(), B_TO_A: direction()},
             "source": {"outbound": link(), "inbound": {**link(), "enabled": False}},
             "destination": {"outbound": link(), "inbound": {**link(), "enabled": False}}}
    for key, value in spec.form_fields().items():
        node = saved
        *parents, leaf = key.split("/")
        for part in parents:
            node = node.setdefault(part, {})
        if value in ("true", "false"):      # checkboxes are stored as booleans
            node[leaf] = value == "true"
        else:
            node[leaf] = float(value) if value.replace(".", "", 1).isdigit() else value
    return saved


@pytest.mark.hardware_free
def test_t0_new_impairments_type_their_fields_method_first():
    fields = EVERYTHING.a_to_b.fields(A_TO_B)
    wan = f"wan/{A_TO_B}"
    assert fields[f"{wan}/delay/method"] == "normal"
    assert fields[f"{wan}/delay/normal/mean"] == "20"
    assert fields[f"{wan}/delay/normal/standard-deviation"] == "5"
    assert fields[f"{wan}/outage/method"] == "periodic"
    assert (fields[f"{wan}/outage/duration"], fields[f"{wan}/outage/interval"]) == ("2", "10")
    assert fields[f"{wan}/reordering/offset"] == "4"
    assert fields[f"{wan}/duplication/probability"] == "1"
    keys = list(fields)
    for block in ("delay", "outage", "reordering", "duplication"):
        method = keys.index(f"{wan}/{block}/method")
        assert all(keys.index(k) > method for k in keys if k.startswith(f"{wan}/{block}/") and k != keys[method])


@pytest.mark.hardware_free
def test_t0_impairment_refuses_what_the_emulator_refuses():
    with pytest.raises(AssertionError, match="3 × jitter"):
        Impairment(delay_ms=10, jitter_ms=5)
    with pytest.raises(AssertionError, match="outage"):
        Impairment(outage_s=2)


@pytest.mark.hardware_free
def test_t0_frame_changing_impairments_are_known():
    assert Impairment(outage_s=1, outage_every_s=5).loses_frames(500)
    assert Impairment(duplicate_pct=1).alters_sequence and Impairment(reorder_pct=1).alters_sequence
    assert not Impairment(delay_ms=20, jitter_ms=5).loses_frames(500)


@pytest.mark.hardware_free
def test_t0_stored_path_reads_back_as_the_same_spec():
    assert WanPathSpec.from_saved(_stored(EVERYTHING)) == EVERYTHING
    assert EVERYTHING.mismatches(_stored(EVERYTHING)) == {}
    assert EVERYTHING.min_cap_mbps == 100


@pytest.mark.hardware_free
def test_t0_stored_path_with_unmodelled_settings_says_which():
    saved = _stored(EVERYTHING)
    saved["wan"][B_TO_A]["delay"]["method"] = "exponential"
    saved["source"]["inbound"]["enabled"] = False
    saved["destination"]["outbound"]["queue"]["algorithm"] = "random-early-detection"
    with pytest.raises(NotModelled, match="exponential.*random-early-detection"):
        WanPathSpec.from_saved(saved)


@pytest.mark.hardware_free
def test_t0_enabled_inbound_link_tightens_the_cap():
    """Presets switch inbound links on (4G LTE does): a-to-b then crosses
    source/outbound and destination/inbound, so its cap is the tighter."""
    saved = _stored(EVERYTHING)
    saved["destination"]["inbound"].update(enabled=True, bandwidth={"rate": 40, "metric": "Mbps"})
    spec = WanPathSpec.from_saved(saved)
    assert spec.a_to_b.bandwidth_mbps == 40 and spec.reverse.bandwidth_mbps == 250


@pytest.mark.hardware_free
def test_t0_uniform_delay_with_reordering_round_trips():
    """The GEO satellite preset's shape (uniform 300-400 ms, may reorder)."""
    geo = WanPathSpec("t0-lib-geo", a_to_b=Impairment(delay_ms=300, delay_max_ms=400,
                                                       allow_reordering=True, bandwidth_mbps=12),
                      b_to_a=Impairment(delay_ms=300, delay_max_ms=400, allow_reordering=True,
                                        bandwidth_mbps=3))
    fields = geo.a_to_b.fields(A_TO_B)
    assert fields[f"wan/{A_TO_B}/delay/method"] == "uniform"
    assert fields[f"wan/{A_TO_B}/delay/reordering"] == "true"
    saved = _stored(geo)
    assert WanPathSpec.from_saved(saved) == geo
    assert geo.mismatches(saved) == {}
    assert geo.a_to_b.mean_delay_ms == 350 and geo.a_to_b.alters_sequence
    assert geo.min_cap_mbps == 3


@pytest.mark.hardware_free
def test_t0_loss_tolerance_widens_only_for_small_runs():
    assert loss_tolerance_pp(1, 1_800_000) == 0.2
    assert loss_tolerance_pp(1, 800) > 1


@pytest.mark.hardware_free
def test_t0_burst_queueing_matches_the_lte_measurement():
    """4G LTE on 2026-10-19: latency rose 13.2 ms over the delay at the
    15 Mbps cap and 15.9 ms at 12.5 Mbps, 1500 B frames."""
    assert round(burst_queue_ms(15, 1500), 1) == 13.2
    assert round(burst_queue_ms(12.5, 1500), 1) == 15.9
    assert burst_queue_ms(None, 1500) == 0

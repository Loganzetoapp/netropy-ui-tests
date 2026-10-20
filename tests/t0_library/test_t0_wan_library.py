"""T0: the WAN emulator half of pages/. Builds a path through the form and
reads back, through the emulator's API, that every field was stored as
typed; edits it; builds one from a preset; and creates an endpoint. Paths
are never applied to traffic (no Default Action, Emulation untouched), so
this generates nothing and is safe while others run. The endpoint test
is the exception that needs care: an endpoint redirects matching traffic
whenever Emulation is on, so it only runs while Engine 2's Emulation is
off."""
import pytest
from playwright.sync_api import Page

from pages import settings
from pages.wan_emulator_page import WanEmulatorPage
from pages.wan_path_spec import EndpointSpec, Impairment, WanPathSpec
from wan_api import WanApi

# Every Impairment field, different per direction, so a swapped direction
# or a field saved to the wrong access link shows up as a mismatch.
PATH = WanPathSpec(
    "t0-lib-probe",
    a_to_b=Impairment(delay_ms=20, jitter_ms=5, loss_pct=1.5, bandwidth_mbps=100, duplicate_pct=1,
                      reorder_pct=2, reorder_offset=4, outage_s=2, outage_every_s=10),
    b_to_a=Impairment(delay_ms=80, delay_max_ms=90, allow_reordering=True, loss_pct=0.25,
                      bandwidth_mbps=250, duplicate_pct=0.5),
)
EDITED = WanPathSpec("t0-lib-probe", a_to_b=Impairment(delay_ms=100))


@pytest.mark.hardware_free
def test_t0_wan_path_form_round_trip(wan_page: Page):
    emulator = WanEmulatorPage(wan_page)
    api = WanApi(settings.WAN_URL, settings.WAN_USER, settings.WAN_PASS)
    emulator.open_engine()
    before = (emulator.emulation_on(), emulator.default_actions())

    with emulator.path_created(PATH):
        saved = [p for p in api.engine(emulator.ENGINE_INDEX)["path"] if p["label"] == PATH.name]
        assert len(saved) == 1, f"expected one path {PATH.name!r}, emulator has {len(saved)}"
        assert PATH.mismatches(saved[0]) == {}

    labels = [p["label"] for p in api.engine(emulator.ENGINE_INDEX).get("path", [])]
    assert PATH.name not in labels
    emulator.open_engine()
    assert (emulator.emulation_on(), emulator.default_actions()) == before


def _stored(api, emulator, name):
    return next((p for p in api.engine(emulator.ENGINE_INDEX)["path"] if p["label"] == name), None)


@pytest.mark.hardware_free
def test_t0_wan_path_edit_is_stored(wan_page: Page):
    """edit_path (T19b's mid-run change) on a path no traffic uses."""
    emulator = WanEmulatorPage(wan_page)
    api = WanApi(settings.WAN_URL, settings.WAN_USER, settings.WAN_PASS)
    with emulator.path_created(PATH):
        emulator.edit_path(EDITED)
        expect_stored = lambda: EDITED.mismatches(_stored(api, emulator, EDITED.name) or {})
        for _ in range(20):
            if not expect_stored():
                break
            wan_page.wait_for_timeout(1_000)  # poll interval: the save is asynchronous
        assert expect_stored() == {}


@pytest.mark.hardware_free
def test_t0_wan_preset_creates_a_path(wan_page: Page):
    """create_path_from_preset (T20): the preset fills the form, the path
    is stored with a cap off the 128 Kbps default, and it's deleted."""
    emulator = WanEmulatorPage(wan_page)
    api = WanApi(settings.WAN_URL, settings.WAN_USER, settings.WAN_PASS)
    name = "t0-lib-preset"
    emulator.open_engine()
    emulator.delete_path(name)
    try:
        emulator.create_path_from_preset(name, "Cellular", "4G LTE")
        saved = _stored(api, emulator, name)
        assert saved is not None, "no path stored after picking a preset"
        bandwidth = saved["source"]["outbound"]["bandwidth"]
        assert (bandwidth["rate"], bandwidth["metric"]) != (128, "Kbps"), saved["source"]
    finally:
        emulator.open_engine()
        emulator.delete_path(name)
    assert _stored(api, emulator, name) is None


@pytest.mark.hardware_free
def test_t0_wan_endpoint_create_and_delete(wan_page: Page):
    """create_endpoint / delete_endpoint (T21), only while Emulation is off
    so the endpoint can't redirect anyone's traffic."""
    emulator = WanEmulatorPage(wan_page)
    emulator.open_engine()
    if emulator.emulation_on():
        pytest.skip("Engine 2 Emulation is on: an endpoint would redirect live traffic")
    path = WanPathSpec("t0-lib-ep-path")
    endpoint = EndpointSpec("t0-lib-ep", 3, "udp", path.name, "10.0.0.1")
    with emulator.path_created(path):
        try:
            emulator.open_engine()
            emulator.create_endpoint(endpoint)
        finally:
            emulator.open_engine()
            emulator.delete_endpoint(endpoint.label)
        assert emulator._endpoint_link(endpoint.label).count() == 0

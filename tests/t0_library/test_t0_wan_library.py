"""T0: the WAN emulator half of pages/. Builds a path through the form and
reads back, through the emulator's API, that every field was stored as
typed. The path is never applied to traffic (no Default Action, Emulation
untouched), so this generates nothing and is safe while others run."""
import pytest
from playwright.sync_api import Page

from pages import settings
from pages.wan_emulator_page import WanEmulatorPage
from pages.wan_path_spec import Impairment, WanPathSpec
from wan_api import WanApi

# Every Impairment field, different per direction, so a swapped direction
# or a field saved to the wrong access link shows up as a mismatch.
PATH = WanPathSpec(
    "t0-lib-probe",
    a_to_b=Impairment(delay_ms=12.5, loss_pct=1.5, bandwidth_mbps=100),
    b_to_a=Impairment(delay_ms=80, loss_pct=0.25, bandwidth_mbps=250),
)


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

"""T0: the WAN bench's pre-run decisions (pages/wan_preflight.py) on
stand-in emulator objects, no hardware: idle -> go; our own leftover ->
cleaned up; someone else's setup -> skip while traffic flows, skip or
borrow when idle (WAN_BORROW_IDLE_ENGINE), and a borrowed setup is put
back exactly, or left alone if someone changed the engine since."""
import pytest

from pages import settings
from pages.errors import PortsBusyError
from pages.wan_emulator_page import EngineState
from pages.wan_preflight import EngineLease, WanPreflight

THEIRS = EngineState(True, {"port-a": "Default Path", "port-b": "Default Path"})
IDLE = EngineState(False, {"port-a": "Bypass", "port-b": "Bypass"})


class FakeEmulator:
    ENGINE_INDEX = 2

    def __init__(self, state, paths=("Default Path",)):
        self.current, self.paths, self.deleted = state, list(paths), []

    def open_engine(self):
        pass

    def state(self):
        return self.current

    def make_idle(self):
        self.current = IDLE

    def set_default_actions(self, actions):
        self.current = EngineState(self.current.emulation, dict(actions))

    def set_emulation(self, on):
        self.current = EngineState(on, self.current.actions)

    def delete_path(self, label):
        self.paths.remove(label)
        self.deleted.append(label)


class FakeApi:
    def __init__(self, emulator, rate=0):
        self.emulator, self.rate = emulator, rate

    def engine(self, index):
        return {"path": [{"label": label, "index": i + 1} for i, label in enumerate(self.emulator.paths)]}

    def stats_summary(self, engine, paths):
        return {"flow": [{"index": i, "rate": self.rate} for i in paths]}


class FakeMetrics:
    def __init__(self):
        self.record = {}


def _preflight(emulator, rate=0, lease=None):
    return WanPreflight(emulator, FakeApi(emulator, rate), FakeMetrics(), lease)


@pytest.fixture(autouse=True)
def _no_sample_wait(monkeypatch):
    monkeypatch.setattr("pages.wan_preflight._TRAFFIC_SAMPLE_GAP_S", 0)


@pytest.mark.hardware_free
def test_t0_preflight_idle_engine_goes_ahead():
    emulator = FakeEmulator(IDLE, paths=[])
    _preflight(emulator)._engine()
    assert emulator.current == IDLE


@pytest.mark.hardware_free
def test_t0_preflight_cleans_up_our_own_leftovers():
    emulator = FakeEmulator(EngineState(True, {"port-a": "t16-loss-5", "port-b": "t16-loss-5"}),
                            paths=["Default Path", "t16-loss-5"])
    check = _preflight(emulator)
    check._engine()
    check._leftover_paths()
    assert emulator.current == IDLE
    assert emulator.deleted == ["t16-loss-5"] and emulator.paths == ["Default Path"]


@pytest.mark.hardware_free
def test_t0_preflight_never_touches_a_setup_with_traffic(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "WAN_BORROW_IDLE_ENGINE", True)
    emulator = FakeEmulator(THEIRS)
    with pytest.raises(PortsBusyError, match="traffic is flowing"):
        _preflight(emulator, rate=40_000, lease=EngineLease(tmp_path / "lease.json"))._engine()
    assert emulator.current == THEIRS


@pytest.mark.hardware_free
def test_t0_preflight_skips_an_idle_setup_unless_borrowing_is_on(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "WAN_BORROW_IDLE_ENGINE", False)
    emulator = FakeEmulator(THEIRS)
    with pytest.raises(PortsBusyError, match="WAN_BORROW_IDLE_ENGINE=true"):
        _preflight(emulator, lease=EngineLease(tmp_path / "lease.json"))._engine()
    assert emulator.current == THEIRS


@pytest.mark.hardware_free
def test_t0_preflight_borrows_and_the_lease_puts_it_back(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "WAN_BORROW_IDLE_ENGINE", True)
    lease_file = tmp_path / "lease.json"
    emulator = FakeEmulator(THEIRS)
    _preflight(emulator, lease=EngineLease(lease_file))._engine()
    assert emulator.current == IDLE and lease_file.exists()

    # A session that died here is recovered by the next one's lease.
    recovered = EngineLease(lease_file)
    assert recovered.original == THEIRS
    assert recovered.restore(emulator).startswith("restored")
    assert emulator.current == THEIRS and not lease_file.exists()


@pytest.mark.hardware_free
def test_t0_lease_leaves_a_changed_engine_alone(tmp_path):
    lease = EngineLease(tmp_path / "lease.json")
    lease.borrow(THEIRS)
    someone_new = EngineState(True, {"port-a": "Their Other Path", "port-b": "Bypass"})
    emulator = FakeEmulator(someone_new)
    assert lease.restore(emulator).startswith("NOT restored")
    assert emulator.current == someone_new and (tmp_path / "lease.json").exists()

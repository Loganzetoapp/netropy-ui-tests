"""T0 — library self-tests: every pages/ method that drives the editor runs
once against the real UI, so a UI change shows up here as "library: X
broken" instead of as 30 unrelated stateful failures.

Hardware-free: each test builds a draft testbed on Ports 1/2 and never
starts it (a draft reserves nothing), then checks what the unit stored
through the Controller's read-only /tests API. Run these first.
"""
import time

import pytest
from playwright.sync_api import Page, expect

from ntg_api import NtgApi
from pages import (
    CreateTestbedPage, DashboardPage, PortSpec, StreamSpec, TestbedEditorPage, TestbedSpec,
    TrafficEngine,
)
from pages import settings

NAME = "T0-Lib-Draft"


@pytest.fixture
def api():
    return NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)


@pytest.fixture
def draft(dashboard: Page):
    board = DashboardPage(dashboard)
    board.remove_testbed(NAME)
    yield NAME
    board.remove_testbed(NAME)


def _stored(api, name, ready=lambda cfg: bool(cfg.get("port")), timeout_s=5):
    """The Controller's stored config once `ready(cfg)` holds, or as it
    stands after `timeout_s`. It can return the old config for ~0.1 s
    after Save's PUT has already answered 200 (probe 2026-10-16), so a
    read straight after save() polls, like a web-first assertion."""
    deadline = time.monotonic() + timeout_s
    cfg = api.test(name)
    while not ready(cfg) and time.monotonic() < deadline:
        time.sleep(0.1)  # poll interval
        cfg = api.test(name)
    ports = {p["port-id"]: p for p in cfg.get("port", [])}
    return cfg, ports


@pytest.mark.hardware_free
@pytest.mark.smoke
def test_t0_dashboard_create_and_remove_testbed(dashboard: Page, draft):
    board = DashboardPage(dashboard)
    tile = board.create_testbed(draft)
    expect(tile).to_have_count(1)
    board.remove_testbed(draft)
    expect(board.testbed_entry(draft)).to_have_count(0)


@pytest.mark.hardware_free
def test_t0_create_testbed_rejects_names_over_15_chars(dashboard: Page):
    with pytest.raises(AssertionError, match="over 15 chars"):
        DashboardPage(dashboard).create_testbed("T0-name-way-too-long")


@pytest.mark.hardware_free
def test_t0_editor_ports_step_rate_direction(dashboard: Page, draft, api):
    board, ed = DashboardPage(dashboard), TestbedEditorPage(dashboard)
    board.create_testbed(draft)
    board.open_editor(draft)
    ed.enable_ports([1, 2], rate=500, unit="Mbps")
    ed.set_direction(1, "tx only")
    ed.set_direction(2, "rx_only")
    ed.add_stream("UDP")
    ed.set_duration(5)
    ed.save()
    _, ports = _stored(api, draft)
    assert sorted(ports) == [1, 2], ports
    assert ports[1].get("rate-mbps") == 500, ports[1]


@pytest.mark.hardware_free
def test_t0_editor_full_spec_is_stored(dashboard: Page, draft, api):
    """TrafficEngine.configure(): every field of a TestbedSpec lands in the
    stored config."""
    spec = TestbedSpec(
        ports={
            1: PortSpec(rate=1, ip="10.20.0.1", cidr=29),
            2: PortSpec(rate=1, ip="10.20.0.2", cidr=29),
        },
        streams=[StreamSpec("UDP", frame_size=512), StreamSpec("TCP", quantity=2)],
        frame_size=1024,
        ramp=(2, 6, 2),
    )
    board, engine = DashboardPage(dashboard), TrafficEngine(dashboard)
    board.create_testbed(draft)
    board.open_editor(draft)
    engine.configure(spec)
    engine.editor.save()
    cfg, ports = _stored(api, draft, ready=lambda c: len(c.get("stream", [])) == 3)
    assert len(cfg.get("stream", [])) == 3, cfg.get("stream")
    assert ports[1].get("rate-mbps") == 1000, ports[1]
    text = repr(cfg)
    for expected in ("10.20.0.1", "10.20.0.2", "512", "1024"):
        assert expected in text, f"{expected} not in stored config: {text[:800]}"


@pytest.mark.hardware_free
def test_t0_editor_load_profile_toggle_and_ramp(dashboard: Page, draft):
    board, ed = DashboardPage(dashboard), TestbedEditorPage(dashboard)
    board.create_testbed(draft)
    board.open_editor(draft)
    ed.enable_ports([1, 2])
    ed.add_stream("UDP")
    ed.set_ramp(3, 10, 3)            # asserts "= 16s" itself
    ed.set_load_profile_enabled(False)
    ed.set_duration(7)               # 0 / 7 / 0
    expect(ed.start_button).to_be_enabled()


@pytest.mark.hardware_free
def test_t0_editor_gateway_next_hop(dashboard: Page, draft, api):
    board, ed = DashboardPage(dashboard), TestbedEditorPage(dashboard)
    board.create_testbed(draft)
    board.open_editor(draft)
    ed.enable_ports([1, 2])
    ed.set_port_address(1, "30.20.20.2", 30, dst_ip="40.0.0.12", gateway_ip="30.20.20.1")
    ed.set_port_address(2, "40.0.0.12", 29, dst_ip="30.20.20.2", gateway_ip="40.0.0.9")
    ed.add_stream("UDP")
    ed.set_duration(5)
    ed.save()
    text = repr(_stored(api, draft, ready=lambda c: "40.0.0.9" in repr(c))[0])
    assert "30.20.20.1" in text and "40.0.0.9" in text, text[:800]


@pytest.mark.hardware_free
def test_t0_speaker1_facade_builds_their_config(dashboard: Page, draft, api):
    """Speaker 1's script shape (pages.zip test_tcp_udp_1500) up to, not
    including, start_test()."""
    tb = CreateTestbedPage(dashboard)
    ports = (1, 2)
    tb.create_testbed(draft, ports)
    tb.ensure_ports_reserved(ports)
    tb.edit_testbed(draft)
    tb.port_config(ports, {1: "bidirectional", 2: "bidirectional"})
    tb.port_line_rate_config(ports, {1: "1", 2: "1"})
    tb.network_config(ports, {
        1: {"ip": "30.20.20.2", "mask": "30", "destination_ip": "40.0.0.12"},
        2: {"ip": "40.0.0.12", "mask": "29", "destination_ip": "30.20.20.2"},
    })
    tb.stream_config((
        {"protocol": "TCP", "name": "tcp-stream", "frame_size": 1500},
        {"protocol": "UDP", "name": "udp-stream", "frame_size": 1500},
    ))
    tb.load_profile_config(10)
    tb.editor.save()
    cfg, _ = _stored(api, draft, ready=lambda c: len(c.get("stream", [])) >= 2)
    names = [s.get("name") for s in cfg.get("stream", [])]
    assert any("tcp-stream" in str(n) for n in names) and any("udp-stream" in str(n) for n in names), names


@pytest.mark.hardware_free
def test_t0_port_holders_reads_ownership(dashboard: Page):
    """Every reserved port is reported busy unless it is held by the
    caller's own testbed, even when the Controller marks it `mine` (the
    login is shared, so `mine` can be someone else's run)."""
    api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
    reserved = {p["port-id"]: p.get("test-name") for p in api.ports() if p.get("reserved")}
    busy = DashboardPage(dashboard).port_holders(range(1, 9))
    assert set(busy) == set(reserved), (busy, reserved)
    for port, holder in reserved.items():
        if holder:
            assert port not in DashboardPage.port_holders([port], own_testbed=holder), (port, holder)

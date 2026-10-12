"""T10 — Speaker 1's example scripts (t15_tests.zip, 2026-10-11), run through
their CreateTestbedPage API unchanged in shape: the config block plus the
same call sequence. The facade (pages/create_TE_testbed_page.py) supplies
the safety the originals lacked: ports held by others are never released,
no fixed sleeps, and start_test() fails unless the run PASSes with real
traffic. Each run lands on the summary sheet.

Changes from the originals: credentials and URL come from .env (the
session login), testbed names are unique per case (all four used
"TE-Test"), and the test functions are named after the plan area.

Stateful: generates real traffic.
"""
import pytest
from playwright.sync_api import Page

from pages import CreateTestbedPage

PAIR_NETWORKS = {
    "a": {"ip": "30.20.20.2", "mask": "30", "destination_ip": "40.0.0.12"},
    "b": {"ip": "40.0.0.12", "mask": "29", "destination_ip": "30.20.20.2"},
}


def _case(name, ports, rate, duration, streams):
    a, b = ports
    return pytest.param(
        name, ports, {a: "bidirectional", b: "bidirectional"}, {a: rate, b: rate},
        {a: PAIR_NETWORKS["a"], b: PAIR_NETWORKS["b"]}, streams, duration, id=name,
    )


CASES = [
    _case("TE-UDP1500-12", (1, 2), "1", 5,
          ({"protocol": "UDP", "name": "udp-stream", "frame_size": 1500},)),
    _case("TE-UDP1500-34", (3, 4), "1", 10,
          ({"protocol": "UDP", "name": "udp-stream", "frame_size": 1500},)),
    _case("TE-TCP1500-34", (3, 4), "1", 10,
          ({"protocol": "TCP", "name": "tcp-stream", "frame_size": 1500},)),
    _case("TE-TCPUDP-12", (1, 2), "1", 10,
          ({"protocol": "TCP", "name": "tcp-stream", "frame_size": 1500},
           {"protocol": "UDP", "name": "udp-stream", "frame_size": 1500})),
]


@pytest.mark.stateful
@pytest.mark.parametrize(
    "testbed_name, ports, port_directions, port_line_rates, port_networks, streams, test_duration",
    CASES,
)
def test_t10_facade_example_scripts(dashboard: Page, run_metrics, testbed_name, ports,
                                    port_directions, port_line_rates, port_networks, streams,
                                    test_duration):
    create_testbed_page = CreateTestbedPage(dashboard, metrics=run_metrics)
    try:
        create_testbed_page.create_testbed(testbed_name, ports)
        create_testbed_page.ensure_ports_reserved(ports)
        create_testbed_page.edit_testbed(testbed_name)
        create_testbed_page.port_config(ports, port_directions)
        create_testbed_page.port_line_rate_config(ports, port_line_rates)
        create_testbed_page.network_config(ports, port_networks)
        create_testbed_page.stream_config(streams)
        create_testbed_page.load_profile_config(test_duration)
        create_testbed_page.start_test(test_duration)
    finally:
        create_testbed_page.cleanup_testbed(testbed_name, ports)

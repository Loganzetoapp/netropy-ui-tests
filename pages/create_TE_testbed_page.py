"""Speaker 1's CreateTestbedPage API (pages.zip, 2026-10-11), kept so their
scripts run unchanged, now backed by the shared page objects. Differences
from the original, all deliberate:

* Ports are never released or deactivated unless the Controller says this
  account holds them (`mine`). The original clicked "Deactivate & release"
  on any port showing Release, which stops other people's runs.
* No fixed sleeps: every step waits for its own result.
* start_test() waits for the saved run and fails unless the NTG verdict
  is pass and traffic was actually sent and received. The original slept
  for duration + 50 s and passed whatever happened.
* NTG 5.0 auto mode reserves ports on Start, so ensure_ports_reserved()
  only checks the ports are free (or ours); it doesn't reserve by hand.
"""
import re

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from pages import settings
from pages.base_page import port_number
from pages.dashboard_page import DashboardPage
from pages.testbed_editor_page import TestbedEditorPage
from pages.testbed_spec import TestbedSpec
from pages.traffic_engine import TrafficEngine


class CreateTestbedPage:
    def __init__(self, page: Page, metrics=None):
        self.page = page
        self.dashboard = DashboardPage(page)
        self.editor = TestbedEditorPage(page)
        self.engine = TrafficEngine(page, metrics)
        self.testbed_name = None
        self.ports = ()
        self._duration = None

    # --- dashboard ----------------------------------------------------
    def testbed_entry(self, testbed_name):
        return self.dashboard.testbed_entry(testbed_name)

    def create_testbed(self, testbed_name, ports=None):
        self.go_home()
        if ports:
            self.dashboard.require_ports_free(ports, own_testbed=testbed_name)
        self.delete_if_exists(testbed_name)
        self.dashboard.create_testbed(testbed_name)
        self.engine.created.append(testbed_name)
        self.testbed_name, self.ports = testbed_name, tuple(ports or ())

    def delete_if_exists(self, testbed_name):
        self.dashboard.remove_testbed(testbed_name)

    def port_row(self, port_number_):
        return self.dashboard.port_row(port_number_)

    def ensure_ports_reserved(self, ports=(3, 4)):
        """5.0 reserves on Start; here we only make sure nobody else holds them."""
        self.dashboard.require_ports_free(ports, own_testbed=self.testbed_name)

    reserve_ports = ensure_ports_reserved
    verify_ports_reserved = ensure_ports_reserved

    def release_port(self, port_number_):
        """Release only a port this account holds."""
        from ntg_api import NtgApi

        api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
        row = next((p for p in api.ports() if p["port-id"] == port_number(port_number_)), None)
        if not row or not row.get("mine"):
            return
        self.go_home()
        self.dashboard.port_row(port_number_).get_by_role("button", name="Release", exact=True).click()
        confirm = self.page.get_by_role("button", name="Deactivate & release", exact=True)
        try:
            confirm.wait_for(state="visible", timeout=2_000)
            confirm.click()
        except PlaywrightTimeoutError:
            pass
        expect(
            self.dashboard.port_row(port_number_).get_by_role("button", name="Reserve", exact=True)
        ).to_be_visible(timeout=30_000)

    def release_ports(self, ports=(3, 4)):
        for p in ports:
            self.release_port(p)

    release_ports_if_reserved = release_ports

    def edit_testbed(self, testbed_name):
        self.dashboard.open_editor(testbed_name)

    def go_home(self):
        self.dashboard.open()

    def cleanup_testbed(self, testbed_name, ports=None):
        """Delete the testbed (deactivating it frees its ports)."""
        self.dashboard.remove_testbed(testbed_name)
        if testbed_name in self.engine.created:
            self.engine.created.remove(testbed_name)

    # --- editor -------------------------------------------------------
    def port_config(self, ports, port_directions):
        self.editor.open_step(1)
        for p in ports:
            if p not in port_directions:
                raise ValueError(f"No direction provided for port {p}; ports are {ports}")
            self.editor.set_port_enabled(p, True)
        for p in ports:
            self.editor.set_direction(p, port_directions[p])

    def port_line_rate_config(self, ports, port_line_rates, unit="Gbps"):
        for p in ports:
            if p not in port_line_rates:
                raise ValueError(f"No line rate provided for port {p}; ports are {ports}")
            self.editor.set_line_rate(p, port_line_rates[p], unit)

    def click_next(self):
        """Kept for old scripts. Every step is reachable without Next (the
        library opens steps directly), so this is a no-op."""

    def network_config(self, ports, port_networks):
        for p in ports:
            cfg = port_networks[p]
            self.editor.set_port_address(p, cfg["ip"], cfg["mask"])
        for p in ports:
            cfg = port_networks[p]
            self.editor.set_port_address(
                p, cfg["ip"], cfg["mask"], dst_ip=cfg.get("destination_ip"), gateway_ip=cfg.get("gateway_ip")
            )

    def stream_config(self, streams):
        index = 0
        for i, stream in enumerate(streams or (), start=1):
            if isinstance(stream, str):
                stream = {"protocol": stream}
            quantity = stream.get("quantity", 1)
            self.editor.add_stream(stream["protocol"], quantity=quantity, name=stream.get("name"))
            for _ in range(quantity):
                if stream.get("frame_size") is not None:
                    self.editor.set_stream_frame_size(index, stream["frame_size"])
                index += 1

    def load_profile_config(self, duration):
        self._duration = int(duration)
        self.editor.set_duration(self._duration)

    def start_test(self, duration=None, assert_pass=True):
        """Start, wait for the saved run, record the summary sheet, and
        (by default) fail unless it passed with real traffic."""
        name = self.testbed_name
        spec = TestbedSpec(ports={}, streams=[], duration_s=int(duration or self._duration))
        self.engine.start(name)
        result = self.engine.wait(name, spec)
        if assert_pass:
            result.assert_passed()
        return result

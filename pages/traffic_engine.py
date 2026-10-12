"""One call from a TestbedSpec to a checked, recorded run:

    result = traffic_engine.run("T10-UDP", SPEC)
    result.assert_passed()

build (create + configure) -> start (crash check on failure) -> wait for
the saved run -> read it through the API -> summary-sheet checks."""
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import Page

from pages import settings
from pages.dashboard_page import DashboardPage
from pages.errors import SystemBadStateError
from pages.run_page import RunPage
from pages.testbed_editor_page import TestbedEditorPage
from pages.testbed_spec import TestbedSpec
from pages.unit_health import UnitHealth

# How long a run may take beyond its configured length: activation,
# the post-run tail, and saving.
_RUN_SLACK_MS = 3 * 60_000


@dataclass
class RunResult:
    testbed: str
    verdict: str          # the NTG's saved verdict, from the Test Reports row
    row_text: str
    ntg: Optional[dict]   # the run digest recorded on the summary sheet
    metrics: object = None

    def assert_passed(self) -> None:
        """NTG verdict is pass AND the summary sheet's enforced checks hold
        (traffic was really sent and received)."""
        failed = self.metrics.failed_checks() if self.metrics else []
        assert self.verdict == "pass" and not failed, (
            f"{self.testbed}: verdict {self.verdict!r}; failed checks "
            f"{[(c['name'], c['measured']) for c in failed]}; saved run row: {self.row_text!r}"
        )


class TrafficEngine:
    """The high-level library: what a traffic test calls."""

    def __init__(self, page: Page, metrics=None):
        self.page = page
        self.metrics = metrics
        self.dashboard = DashboardPage(page)
        self.editor = TestbedEditorPage(page)
        self.runs = RunPage(page)
        self.health = UnitHealth(page)
        self.created = []

    # --- build --------------------------------------------------------
    def create(self, name: str, spec: TestbedSpec) -> None:
        """Fresh testbed `name` configured per `spec`, left open in the editor."""
        self.dashboard.require_ports_free(spec.port_numbers, own_testbed=name)
        self.dashboard.remove_testbed(name)
        self.dashboard.create_testbed(name)
        self.created.append(name)
        self.dashboard.open_editor(name)
        self.configure(spec)

    def configure(self, spec: TestbedSpec) -> None:
        ed = self.editor
        ed.open_step(1)
        for n in spec.port_numbers:
            ed.set_port_enabled(n, True)
        for n, p in spec.ports.items():
            if p.direction != "bidirectional":
                ed.set_direction(n, p.direction)
            if p.peer is not None:
                ed.set_peer(n, p.peer)
            if p.rate is not None:
                ed.set_line_rate(n, p.rate, p.unit)
        addressed = [n for n, p in spec.ports.items() if p.ip]
        for n in addressed:
            p = spec.ports[n]
            ed.set_port_address(n, p.ip, p.cidr or 32)
        for n in addressed:
            p = spec.ports[n]
            dst = spec.destination_for(n)
            if dst or p.gateway_ip:
                ed.set_port_address(n, p.ip, p.cidr or 32, dst_ip=dst, gateway_ip=p.gateway_ip)
        for s in spec.streams:
            ed.add_stream(s.protocol, quantity=s.quantity, name=s.name)
        if spec.frame_size:
            ed.set_all_frame_sizes(spec.frame_size)
        for i, s in enumerate(self._expanded_streams(spec)):
            if s.frame_size:
                ed.set_stream_frame_size(i, s.frame_size)
        if spec.ramp:
            ed.set_ramp(*spec.ramp)
        else:
            ed.set_duration(spec.duration_s)

    @staticmethod
    def _expanded_streams(spec):
        for s in spec.streams:
            for _ in range(s.quantity):
                yield s

    # --- run ----------------------------------------------------------
    def start(self, name: str) -> None:
        """Start from the editor; on failure decide system vs test failure."""
        try:
            self.editor.start()
        except Exception as exc:
            self.health.diagnose_failed_start(name, exc)

    def wait(self, name: str, spec: TestbedSpec, run_number: int = 1, label: str = "run") -> RunResult:
        try:
            row = self.runs.wait_for_run_to_finish(
                run_number, timeout=spec.run_seconds * 1000 + _RUN_SLACK_MS
            )
        except SystemBadStateError:
            # A lost run is a system failure; say whether the unit is still up.
            self.health.assert_healthy(context=f"{name} run #{run_number} lost", testbed=name)
            raise
        verdict, row_text = self.runs.verdict(row), row.inner_text()
        digest = self.record(name, spec, label)
        return RunResult(name, verdict, row_text, digest, self.metrics)

    def run(self, name: str, spec: TestbedSpec, label: str = "run") -> RunResult:
        self.create(name, spec)
        self.start(name)
        return self.wait(name, spec, label=label)

    # --- summary sheet --------------------------------------------------
    def record(self, name: str, spec: TestbedSpec, label: str) -> Optional[dict]:
        """Read the saved run through the API and add it, plus the standard
        checks, to the summary sheet. Without a metrics recorder this is a
        no-op (hardware-free use)."""
        if self.metrics is None:
            return None
        from ntg_api import NtgApi
        from run_metrics import capture_ntg_run, standard_checks

        api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
        if self.metrics.record.get("unit") is None:
            system = api.system()
            self.metrics.set_unit({
                "model": system.get("model"), "version": system.get("version"),
                "target": settings.NTG_URL,
            })
        digest, saved, config = capture_ntg_run(api, name)
        self.metrics.add_run(label, ntg=digest, series={"ntg": saved.get("sample"), "ntg-config": config})
        standard_checks(self.metrics, label, digest, expected_seconds=spec.run_seconds,
                        expect_traffic=spec.expect_traffic)
        return digest

    # --- teardown -----------------------------------------------------
    def cleanup(self) -> None:
        """Remove every testbed this engine created (and only those)."""
        for name in reversed(self.created):
            self.dashboard.remove_testbed(name)
        self.created.clear()

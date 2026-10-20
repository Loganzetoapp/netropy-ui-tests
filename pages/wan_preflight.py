"""Pre-run checks and set-up for the WAN bench (NTG Port 3 -> emulator
Engine 2 -> NTG Port 4). WanBench runs them before a test's first run;
each condition is checked, set up when that is safe, and recorded on the
summary sheet under "preflight". A condition that can't be met safely
skips the test with the reason, and is never "fixed" by taking over
someone else's setup.

| Condition | When not met |
|---|---|
| NTG Controller healthy | system failure (the unit is down) |
| Ports 3/4 free, or held by this test's own testbed | skip: someone else's testbed |
| Ports 3/4 links up (waits up to 30 s: they flap) at a speed >= the spec's rate | link still down: system failure. Too slow: fail, this spec can't run on this bench |
| Engine 2 idle: Emulation off, both Default Actions Bypass | our own leftover (a t0-lib-/t15-/t16-/t17- path) is cleaned up. Someone else's setup: skip while traffic flows through it; when it's idle, borrow it if WAN_BORROW_IDLE_ENGINE=true (put back at session end, see EngineLease), else skip and say how to allow it |
| No leftover endpoints or paths of ours on Engine 2 | deleted (endpoints first: a path an endpoint uses can't be deleted) |

Why borrowing is opt-in: from the emulator's settings alone, a setup
someone parked looks the same as one they're about to use again. The
person running the suite decides, once, in .env.
"""
import json
import time
from dataclasses import asdict
from typing import Dict, Optional

from pages import settings
from pages.dashboard_page import DashboardPage
from pages.errors import PortsBusyError, SystemBadStateError
from pages.wan_emulator_page import EngineState

# Path names the suite's own tests create (WanPathSpec names).
# Endpoints (T21) are named after their path, so the same prefixes cover them.
OUR_PATH_PREFIXES = ("t0-lib-", "t15-", "t16-", "t17-", "t18-", "t19-", "t20-", "t21-")
LEASE_FILE = settings.ROOT / "results" / "wan-engine-borrowed.json"
# Traffic through the engine is sampled twice this far apart: the
# emulator's `rate` is a one-second figure.
_TRAFFIC_SAMPLE_GAP_S = 2
# How long a flapping NTG port link gets to come back before the run is
# called a system failure.
_LINK_SETTLE_S = 30


def is_ours(label: str) -> bool:
    """A path one of this suite's own tests created."""
    return label.startswith(OUR_PATH_PREFIXES)


class EngineLease:
    """Someone else's idle Engine 2 setup, borrowed for one test session
    and put back at its end (the session-scoped `wan_engine_lease`
    fixture). The original state is written to LEASE_FILE until it has
    been put back, so a session that dies mid-borrow is restored by the
    next one instead of being forgotten."""

    def __init__(self, path=LEASE_FILE):
        self.path = path
        self.original: Optional[EngineState] = None
        if path.exists():
            self.original = EngineState(**json.loads(path.read_text()))

    def borrow(self, state: EngineState) -> None:
        if self.original is None:
            self.original = state
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(state), indent=1))

    def restore(self, emulator) -> str:
        """Put the borrowed setup back, if there is one. Only from an idle
        engine: if someone has set it up differently since, leave theirs
        alone and keep the record."""
        if self.original is None:
            return "nothing borrowed"
        emulator.open_engine()
        now = emulator.state()
        if not now.idle:
            return (f"NOT restored: Engine 2 changed since it was borrowed ({now}); "
                    f"original kept in {self.path}")
        emulator.set_default_actions(self.original.actions)
        emulator.set_emulation(self.original.emulation)
        restored, self.original = self.original, None
        self.path.unlink(missing_ok=True)
        return f"restored {restored}"


class WanPreflight:
    def __init__(self, emulator, api, metrics, lease: Optional[EngineLease]):
        self.emulator, self.api, self.metrics, self.lease = emulator, api, metrics, lease
        self.record = []

    def _note(self, condition: str, result: str) -> None:
        self.record.append({"condition": condition, "result": result})
        self.metrics.record["preflight"] = self.record

    def run(self, testbed: str, spec) -> None:
        self._ntg(testbed, spec)
        self._engine()
        self._leftover_paths()

    # --- NTG ------------------------------------------------------------
    def _ntg(self, testbed: str, spec) -> None:
        from ntg_api import NtgApi

        api = NtgApi(settings.NTG_URL, settings.NTG_USER, settings.NTG_PASS)
        health = api.health()
        if health.get("status") != "ok":
            raise SystemBadStateError(f"NTG Controller not healthy before the run: {health}")
        self._note("NTG Controller healthy", "ok")

        busy = DashboardPage.port_holders(spec.port_numbers, own_testbed=testbed)
        if busy:
            self._note("Ports free", f"busy: {busy}")
            raise PortsBusyError("Ports in use by someone else: "
                                 + ", ".join(f"Port {n} by {who}" for n, who in sorted(busy.items())))
        self._note(f"Ports {'/'.join(map(str, spec.port_numbers))} free", "ok")

        links = self._links_up(api, spec.port_numbers)
        for port, port_spec in spec.ports.items():
            rate, speed = port_spec.rate_mbps, links[port]
            assert rate is None or rate <= speed, (
                f"Port {port} links at {speed} Mbps, below the spec's {rate} Mbps: this spec can't run here"
            )
        self._note("Links up, at speeds that cover the spec's rates", f"ok {links}")

    def _links_up(self, api, ports) -> Dict[int, int]:
        """{port: Mbps} once every port's link is up at a real speed. Port
        links on this bench flap ("NTG 5.0: Port 4 link speed changes on its
        own" in netropy-ui-findings.md: 0 Mbps or oper-status "unknown" for a
        few seconds, seen again 2026-10-16), so wait them out; a link still
        down after that is the unit's state, not the test's fault."""
        deadline = time.monotonic() + _LINK_SETTLE_S
        while True:
            state = {}
            for p in api.ports():
                if p["port-id"] in ports:
                    live = p.get("state") or {}
                    # Not the top-level `link`: it's a stored value (see NtgApi.ports).
                    state[p["port-id"]] = (live.get("oper-status"), live.get("speed-mbps") or 0)
            if all(status == "up" and speed for status, speed in state.values()):
                return {port: speed for port, (_, speed) in state.items()}
            if time.monotonic() >= deadline:
                self._note("Links up", f"not up after {_LINK_SETTLE_S}s: {state}")
                raise SystemBadStateError(
                    f"NTG port link(s) not up after {_LINK_SETTLE_S}s (oper-status, Mbps): {state}. "
                    "Known flapping on this bench; see netropy-ui-findings.md."
                )
            time.sleep(1)  # poll interval

    # --- emulator ---------------------------------------------------------
    def _engine(self) -> None:
        self.emulator.open_engine()
        state = self.emulator.state()
        if state.idle:
            self._note("Engine 2 idle", "ok")
            return
        if any(is_ours(label) for label in state.actions.values()):
            self.emulator.make_idle()
            self._note("Engine 2 idle", f"cleaned up our own leftover {state}")
            return
        rate = self._traffic_rate()
        if rate:
            self._note("Engine 2 idle", f"in use by someone else, traffic flowing ({rate}): skipped")
            raise PortsBusyError(f"WAN emulator Engine 2 is in use: traffic is flowing through it ({state})")
        if not settings.WAN_BORROW_IDLE_ENGINE:
            self._note("Engine 2 idle", f"someone else's idle setup {state}: skipped (borrowing off)")
            raise PortsBusyError(
                f"WAN emulator Engine 2 has someone else's setup ({state}) but no traffic. "
                "Set WAN_BORROW_IDLE_ENGINE=true in .env to let the tests borrow an idle engine "
                "and put it back afterwards, or set it to Emulation off + Bypass by hand."
            )
        self.lease.borrow(state)
        self.emulator.make_idle()
        self._note("Engine 2 idle", f"borrowed someone else's idle setup {state}; restored at session end")

    def _traffic_rate(self) -> int:
        """Frames per second through any of Engine 2's paths (Bypass
        included), the larger of two samples."""
        engine = self.api.engine(self.emulator.ENGINE_INDEX)
        indices = [0] + [p["index"] for p in engine.get("path", [])]
        peak = 0
        for sample in range(2):
            if sample:
                time.sleep(_TRAFFIC_SAMPLE_GAP_S)  # the emulator's rate is a 1 s figure
            flows = self.api.stats_summary(self.emulator.ENGINE_INDEX, indices)["flow"]
            peak = max(peak, sum(f.get("rate") or 0 for f in flows))
        return peak

    def _leftover_paths(self) -> None:
        engine = self.api.engine(self.emulator.ENGINE_INDEX)
        endpoints = [e["label"] for e in engine.get("endpoint", []) if is_ours(e.get("label", ""))]
        leftovers = [p["label"] for p in engine.get("path", []) if is_ours(p["label"])]
        if not endpoints and not leftovers:
            self._note("No leftover endpoints or paths of ours", "ok")
            return
        self.emulator.open_engine()
        for label in endpoints:
            self.emulator.delete_endpoint(label)
        for label in leftovers:
            self.emulator.delete_path(label)
        self._note("No leftover endpoints or paths of ours",
                   f"deleted endpoints {endpoints}, paths {leftovers}")

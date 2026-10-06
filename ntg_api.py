"""Read-only client for the traffic generator's Controller API (/ctrl/v1).

Step 1 of docs/wan-integration-plan.md: the suite still DRIVES the NTG
through its UI (that's what it tests). This client only READS: status,
stats and saved runs, for cross-checks against the WAN emulator, richer
results and, later, the live dashboard. It has no method that changes
anything on the unit, and it should stay that way.

Auth: POST /ctrl/v1/login returns a `session-token`, sent as a Bearer
header. (The OpenAPI text says the browser needs no header; on 5.x
builds every route but /health answers 401 without it.)

The one hard rule, from the engineer's notes (reference memory): never
read /stats for a testbed that has stopped until /runs shows the new run
record, because that request can crash the Controller. live_stats()
therefore refuses unless the datapath is RUNNING; finished runs are read
through runs()/run_summary() instead.
"""
import os

import requests

RUNNING = "RUNNING"


class StatsNotSafeError(RuntimeError):
    """Reading live /stats now could crash the Controller (see module doc)."""


class NtgApi:
    def __init__(self, url: str, user: str, password: str, timeout: float = 10):
        self.base = url.rstrip("/") + "/ctrl/v1"
        self.user, self.password, self.timeout = user, password, timeout
        self.session = requests.Session()

    @classmethod
    def from_env(cls) -> "NtgApi":
        return cls(os.environ["NETROPY_URL"], os.environ["NETROPY_USER"], os.environ["NETROPY_PASS"])

    def login(self) -> None:
        r = self.session.post(
            self.base + "/login",
            json={"username": self.user, "password": self.password},
            timeout=self.timeout,
        )
        r.raise_for_status()
        self.session.headers["Authorization"] = "Bearer " + r.json()["session-token"]

    def _get(self, path: str, **params):
        if "Authorization" not in self.session.headers:
            self.login()
        r = self.session.get(self.base + path, params=params or None, timeout=self.timeout)
        if r.status_code == 401:  # session expired: log in again once
            self.login()
            r = self.session.get(self.base + path, params=params or None, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # --- unit ---------------------------------------------------------
    def health(self) -> dict:
        """Controller liveness. Only proves the process answers; see the
        reference notes for what it does NOT cover."""
        r = self.session.get(self.base + "/health", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def system(self) -> dict:
        return self._get("/system")

    def ports(self) -> list:
        """Port rows. Don't use `link` to judge a link: it's a stored
        value that release forces back to "up"."""
        return self._get("/units/local/ports")["ports"]

    def tests(self) -> list:
        return self._get("/tests")["tests"]

    # --- one testbed --------------------------------------------------
    def test(self, name: str) -> dict:
        """The stored config: port[] (rate-mbps, speed-mbps, host addressing),
        stream[], and config (load profile)."""
        return self._get(f"/tests/{name}")

    def status(self, name: str) -> dict:
        return self._get(f"/tests/{name}/status")

    def datapath_state(self, name: str):
        """LEARNING / RUNNING / ERROR …, or None when the testbed is inactive."""
        return (self.status(name).get("app-manager") or {}).get("datapath-state")

    def runs(self, name: str) -> list:
        """Saved runs, oldest first (run-id is lexically sortable)."""
        return sorted(self._get(f"/tests/{name}/runs")["runs"], key=lambda r: r["run-id"])

    def latest_run(self, name: str):
        runs = self.runs(name)
        return runs[-1] if runs else None

    def run(self, name: str, run_id: str) -> dict:
        """The full saved run: same shape as live stats (summary, port[],
        flow[] with direction[], sample[] per second, event[], stages)."""
        return self._get(f"/tests/{name}/runs/{run_id}")

    def run_summary(self, name: str, run_id: str) -> dict:
        return self._get(f"/tests/{name}/runs/{run_id}/summary")

    def run_stages(self, name: str, run_id: str) -> dict:
        return self._get(f"/tests/{name}/runs/{run_id}/stages")

    def run_criteria(self, name: str, run_id: str) -> dict:
        return self._get(f"/tests/{name}/runs/{run_id}/criteria")

    def live_stats(self, name: str, since: float = None, streams: bool = True) -> dict:
        """Live stats for a RUNNING testbed. `since` is run-relative
        seconds (the sample[].at of the last poll) for incremental reads.
        Refuses unless the datapath is RUNNING (see module doc)."""
        state = self.datapath_state(name)
        if state != RUNNING:
            raise StatsNotSafeError(
                f"{name}: datapath is {state!r}, not RUNNING; read the saved run via runs() instead"
            )
        params = {"streams": 1} if streams else {}
        if since is not None:
            params["since"] = since
        return self._get(f"/tests/{name}/stats", **params)

"""Read-only client for the WAN emulator's API (Netropy 10G2, /api).

Step 1 of docs/wan-integration-plan.md. Tests configure the emulator
through wan_emulator.py (its UI); this client only READS config, port
state and statistics. Its only POSTs are the two stats RPCs, which the
emulator's own UI also calls every second. Nothing here changes the box.

Stats model (YANG `apposite-statistics`), per path and direction
("a-to-b" = the engine's first port to its second; for Engine 2 that's
emulator port 3 -> 4):
  * rate / frames / bytes / drops: traffic that entered the path
  * wan: drops, duplicates, reorders, corruptions (what the emulator did)
  * inflow / outflow: the access links, incl. queue length and drops
Path index 0 is Bypass; a created path has its own `index`.
The emulator applies latency but does not measure it; only the NTG does.

Per-second history comes from get-stats-records, addressed by the
summary's `current` sequence number (one step per second).
"""
import os

import requests

STATS_RPC = "/api/apposite-netropy-device:"
METRICS = (
    "overall-rate", "overall-frames", "overall-bytes", "overall-drops",
    "wan-drops", "wan-reorders", "wan-duplicates", "wan-corruptions",
    "inflow-rate", "inflow-queue-length", "inflow-queue-drops",
    "outflow-rate", "outflow-queue-length", "outflow-queue-drops",
)


class WanApi:
    def __init__(self, url: str, user: str, password: str, timeout: float = 10):
        self.base = url.rstrip("/")
        self.user, self.password, self.timeout = user, password, timeout
        self.session = requests.Session()

    @classmethod
    def from_env(cls) -> "WanApi":
        return cls(
            os.environ["WAN_EMULATOR_URL"],
            os.environ["WAN_EMULATOR_USER"],
            os.environ["WAN_EMULATOR_PASS"],
        )

    def login(self) -> None:
        r = self.session.post(
            self.base + "/login",
            data={"username": self.user, "password": self.password},
            timeout=self.timeout,
        )
        r.raise_for_status()

    def _request(self, method: str, path: str, **kwargs):
        if not self.session.cookies:
            self.login()
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", {"Accept": "application/json"})
        r = self.session.request(method, self.base + path, **kwargs)
        # An expired session redirects to /login (HTML) instead of a 401.
        if r.status_code == 401 or "json" not in r.headers.get("content-type", ""):
            self.login()
            r = self.session.request(method, self.base + path, **kwargs)
        r.raise_for_status()
        return r.json()

    # --- config / state -----------------------------------------------
    def device(self) -> dict:
        """Model, firmware, serial, and port link speeds."""
        return self._request("GET", "/api/apposite-netropy-system:device")[
            "apposite-netropy-system:device"
        ]

    def engine(self, index: int) -> dict:
        """One engine: status (emulation, buffers, log), default-action,
        and path[] (each with id, index, label and its impairments)."""
        engines = self._request("GET", "/api/apposite-wan-emulator:engine")[
            "apposite-wan-emulator:engine"
        ]
        return next(e for e in engines if e["index"] == index)

    def path_index(self, engine: int, label: str) -> int:
        """The stats index of the path called `label` ("Bypass" is 0)."""
        if label == "Bypass":
            return 0
        for path in self.engine(engine)["path"]:
            if path["label"] == label:
                return path["index"]
        raise KeyError(f"no path {label!r} on engine {engine}")

    # --- statistics ---------------------------------------------------
    def stats_summary(self, engine: int, paths=(0,)) -> dict:
        """Cumulative counters per path and direction, plus `current`, the
        sequence number of the newest one-second record."""
        return self._request(
            "POST", STATS_RPC + "get-stats-summary", json={"engine": engine, "paths": list(paths)}
        )

    def flows(self, engine: int, paths=(0,)) -> dict:
        """stats_summary() reshaped to {(path index, direction): flow}."""
        summary = self.stats_summary(engine, paths)
        return {(f["index"], f["direction"]): f for f in summary["flow"]}

    def stats_records(self, engine: int, paths=(0,), metrics=METRICS, start=None, end=None) -> dict:
        """Per-second values for each (path, direction, metric) between the
        `start` and `end` sequence numbers (inclusive)."""
        body = {"engine": engine, "paths": list(paths), "metrics": list(metrics)}
        if start is not None:
            body["start"] = start
        if end is not None:
            body["end"] = end
        return self._request("POST", STATS_RPC + "get-stats-records", json=body)

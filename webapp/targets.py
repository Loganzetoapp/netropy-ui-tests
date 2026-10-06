"""Which Netropy box a dashboard-triggered run points at.

The suite itself reads NETROPY_URL (conftest.py). The dashboard lets the
person clicking Run pick a box per run — a known preset or a custom
URL — and passes it to the pytest subprocess as NETROPY_URL, so the
suite needs no changes to support more than one box.
"""
from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

# The boxes the team actually uses. The first entry is the default when
# .env doesn't set NETROPY_URL to something else.
PRESETS = [
    # Ports 3 & 4 run through WAN emulator .213 Engine 2 (T15 uses it).
    {"label": "NTG lab unit (ports 3 & 4, via WAN .213)", "url": "http://192.168.173.212"},
    {"label": "Legacy NTG 4.0 VM", "url": "http://192.168.173.111:8080"},
]
# .89 (the first 5.0 unit) stopped answering on 2026-10-05; dropped so a
# browser that remembered it falls back to the default instead.

_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


def normalize_target_url(raw: str) -> str:
    """Return a canonical `scheme://host[:port]` for a user-typed target,
    or raise ValueError with a message fit to show the user.

    Accepts a bare IP/hostname (http:// is assumed). Rejects paths, query
    strings and embedded credentials — this value ends up in a subprocess
    environment and in run history, so it should only ever be a box
    address."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("Enter an IP address or URL for the target box.")
    if "://" not in value:
        value = "http://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Target must use http:// or https://.")
    if parts.username or parts.password:
        raise ValueError("Don't put credentials in the target URL — they come from .env.")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("Target should be just the box address, e.g. http://192.168.173.89")
    host = parts.hostname or ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME_RE.match(host):
            raise ValueError(f"{host or raw!r} isn't a valid IP address or hostname.")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("Port must be a number between 1 and 65535.")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return f"{parts.scheme}://{netloc}"


def default_target() -> str:
    """The .env NETROPY_URL if set and valid, else the first preset."""
    env_url = os.environ.get("NETROPY_URL", "")
    try:
        return normalize_target_url(env_url)
    except ValueError:
        return PRESETS[0]["url"]


def list_targets() -> dict:
    default = default_target()
    presets = list(PRESETS)
    if not any(p["url"] == default for p in presets):
        presets.insert(0, {"label": "From .env", "url": default})
    return {"default": default, "presets": presets}

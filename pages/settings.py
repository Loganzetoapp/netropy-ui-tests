"""Where the library gets its targets and credentials: `.env` at the repo
root, never hardcoded (CLAUDE.md). Imported by every page object."""
import os
import pathlib

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

NTG_URL = os.environ.get("NETROPY_URL", "").rstrip("/")
NTG_USER = os.environ.get("NETROPY_USER", "")
NTG_PASS = os.environ.get("NETROPY_PASS", "")

WAN_URL = os.environ.get("WAN_EMULATOR_URL", "").rstrip("/")
WAN_USER = os.environ.get("WAN_EMULATOR_USER", "")
WAN_PASS = os.environ.get("WAN_EMULATOR_PASS", "")

# The appliance saves a testbed name longer than this, then permanently
# 502s on activate for it (project bugs, 2026-09-09).
MAX_TESTBED_NAME_LEN = 15

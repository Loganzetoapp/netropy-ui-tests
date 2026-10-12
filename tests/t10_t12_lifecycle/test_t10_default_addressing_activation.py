"""T10 — diagnostic: does activation succeed with DEFAULT (random) host
addressing, when every other lifecycle test in this suite (which
explicitly sets custom static Source/Dest IP + Dest MAC in the Network
Configuration wizard step) has been 502ing on activate all session
(2026-09-08)?

Built specifically to cross-investigate against a manually-created testbed
named "xx" that Logan reported activating and running successfully around
the same time all 7 of this session's automated attempts 502'd. Pulling
xx's saved config via `GET /ctrl/v1/tests/xx` (the same endpoint the UI
itself calls) showed:
    "host": {"ip-type": "random", "mac-type": "random"}   (both ports)
    "rate-mbps": 10000                                    (left at default)
xx never visited the Network Configuration step at all — every field that
step would set was left at its default. That's the one config difference
found between "activated fine" (xx) and "502'd" (every automated test
today) — not line rate, not port pair, not protocol (all already ruled
out this session, see project_bugs_found memory).

This test deliberately skips Wizard step 2 (Network Configuration)
entirely to isolate that one variable — same port-toggle/stream/load-
profile flow as the other lifecycle tests otherwise. If this activates
cleanly where the others didn't, custom addressing is implicated; if it
also 502s, this hypothesis is ruled out too and the 502 is genuinely
config-independent.

Stateful: generates real traffic on shared hardware if activation
succeeds.

NTG 5.0 rewrite (2026-09-30): same isolation as before — ports on, line
rate left at its default, Network Configuration step never visited, one
UDP stream, 10/26/10 ramp — built with the shared conftest helpers and
started via Start -> "Testbed is Inactive" -> Continue.
"""
import pytest
from playwright.sync_api import Page

from conftest import (
    add_stream,
    assert_activatable_name,
    create_testbed,
    enable_ports,
    open_editor,
    remove_testbed,
    assert_run_passed,
    set_ramp,
    start_testbed,
    wait_for_run_to_finish,
)

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-DefaultAddr"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]


@pytest.fixture
def clean_testbed(dashboard: Page):
    remove_testbed(dashboard, TESTBED_NAME)
    yield
    remove_testbed(dashboard, TESTBED_NAME)


@pytest.mark.stateful
def test_t10_default_addressing_activation(dashboard: Page, clean_testbed):
    page = dashboard
    create_testbed(page, TESTBED_NAME)
    open_editor(page, TESTBED_NAME)
    enable_ports(page, PORTS)  # line rate deliberately left at default
    add_stream(page, "UDP")
    set_ramp(page, up=10, hold=26, down=10)

    start_testbed(page)
    run = wait_for_run_to_finish(page, timeout=46_000 + 3 * 60_000)

    assert_run_passed(run)

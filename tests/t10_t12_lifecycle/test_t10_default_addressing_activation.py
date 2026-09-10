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
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_activatable_name

# Testbed name must stay <= 15 chars: the backend can create and save a
# longer name but then 502s on activate (see project-bugs-found, 2026-09-09).
TESTBED_NAME = "T10-DefaultAddr"
assert_activatable_name(TESTBED_NAME)
PORTS = ["Port 1", "Port 2"]
BUFFER_MS = 400


def _buffer(page: Page):
    page.wait_for_timeout(BUFFER_MS)


def _testbed_tile(page: Page):
    return page.locator(".tb-tile").filter(has_text=TESTBED_NAME)


def _delete_testbed_if_present(page: Page):
    tile = _testbed_tile(page)
    if tile.count() > 0:
        tile.locator("button").nth(2).click()
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.is_visible():
            confirm.click()
        expect(_testbed_tile(page)).to_have_count(0, timeout=10000)


def _release_ports(page: Page):
    dashboard_btn = page.get_by_role("button", name="← Dashboard")
    if dashboard_btn.is_visible():
        dashboard_btn.click()
        _buffer(page)
        discard_btn = page.get_by_role("button", name="Discard", exact=True)
        if discard_btn.is_visible():
            discard_btn.click()
    else:
        page.goto("/")
    expect(page.get_by_text("Port Status")).to_be_visible(timeout=20000)
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        release_btn = row.get_by_role("button", name="Release")
        if release_btn.is_visible():
            release_btn.click()
            confirm = page.get_by_role("button", name="Deactivate & release")
            if confirm.is_visible():
                confirm.click()
            expect(row.get_by_text("Available", exact=True)).to_be_visible(timeout=10000)


@pytest.fixture
def clean_testbed(dashboard: Page):
    _delete_testbed_if_present(dashboard)
    yield
    _release_ports(dashboard)
    _delete_testbed_if_present(dashboard)


@pytest.mark.stateful
def test_t10_default_addressing_activation(dashboard: Page, clean_testbed):
    page = dashboard

    # --- Reserve Port 1 and Port 2 ---
    for port_label in PORTS:
        row = page.get_by_role("row", name=port_label)
        expect(row.get_by_text("Available", exact=True)).to_be_visible()
        row.get_by_role("button", name="Reserve").click()
        _buffer(page)
        expect(row.get_by_text("Reserved", exact=True)).to_be_visible(timeout=10000)

    # --- Create testbed ---
    page.get_by_role("button", name="✚ Create Testbed", exact=True).click()
    _buffer(page)
    page.get_by_role("button", name="Traffic Engine").click()
    _buffer(page)
    page.get_by_role("textbox", name="e.g. web-perf-").fill(TESTBED_NAME)
    _buffer(page)
    page.get_by_role("button", name="Create draft").click()
    _buffer(page)

    # --- Wizard step 1: Ports — enable Port 1 & Port 2, LEAVE line rate at
    # its default (10 Gbps) — deliberately not touching it, matching xx's
    # saved config (rate-mbps: 10000, i.e. untouched).
    _testbed_tile(page).get_by_role("button", name="Edit").click()
    _buffer(page)
    page.locator("tr:nth-child(1) > td > div > .toggle > .track").click()
    _buffer(page)
    page.locator("tr:nth-child(2) > td > div > .toggle > .track").click()
    _buffer(page)

    # --- Wizard step 2: Network Configuration — DELIBERATELY SKIPPED.
    # This is the one variable under test: every other lifecycle test in
    # this suite visits this step and sets custom static Source/Dest IP +
    # Dest MAC. xx's saved config shows default random IP/MAC on both
    # ports, meaning it never touched this step. Not clicking into "2
    # Network Configuration" at all here — leaving both ports on whatever
    # the wizard defaults to (random host addressing per xx's config).

    # --- Wizard step 3: Streams — add a single default stream, untouched
    # frame size (matches xx: udp-1, frame-size 1500, defaults throughout).
    page.get_by_role("button", name="3 Streams traffic flows — at").click()
    _buffer(page)
    page.get_by_role("button", name="✚ Add Stream").click()
    _buffer(page)
    add_stream_btn = page.get_by_role("button", name="Add stream", exact=True)
    if add_stream_btn.is_visible():
        add_stream_btn.click()
        _buffer(page)
    expect(page.get_by_role("button", name="UDP Edit UDP").first).to_be_visible()

    # --- Wizard step 4: Traffic and Load Profile — mirror xx's saved
    # values (ramp-up 10s, hold/duration 26s, ramp-down 10s = 46s total).
    page.get_by_role("button", name="4 Traffic and Load Profile").click()
    _buffer(page)
    page.locator("div:nth-child(2) > div > .toggle > .track").click()
    _buffer(page)
    ramp_input = page.locator(".fc > input").first
    if ramp_input.count() == 0 or not ramp_input.is_visible():
        page.locator("div:nth-child(2) > div > .toggle > .track").click()
        _buffer(page)
    page.locator(".fc > input").first.fill("10")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").fill("26")
    _buffer(page)
    page.locator("div:nth-child(2) > .fc > input").press("Enter")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").fill("10")
    _buffer(page)
    page.locator("div:nth-child(3) > .fc > input").press("Enter")
    _buffer(page)
    page.get_by_role("button", name="Apply", exact=True).click()
    _buffer(page)

    # --- Activate / start traffic ---
    expect(page.get_by_role("button", name="Deactivate")).to_be_visible(timeout=75000)
    page.get_by_role("button", name="Start").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

    # --- Wait for the run to finish naturally ---
    tile = _testbed_tile(page)
    expect(tile.get_by_role("button", name="Stop")).to_be_visible(timeout=15000)
    expect(tile.get_by_role("button", name="Stop")).to_have_count(0, timeout=90000)

    # "Reports: N" only appears once the testbed is deactivated (see project
    # bugs memory, 2026-08-28) — at this point it's still active, so the
    # same run-history page is reached via "Stats" instead.
    tile.get_by_role("button", name="Stats").click()
    expect(page.get_by_text("pass", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="← Dashboard").click()
    expect(page.get_by_text("Port Status")).to_be_visible()

"""T3 — Reserved By / Test Name columns populate correctly while a
testbed is active.

Confirmed by exploration: the dashboard's Port Status table shows
Reserved By "test (you)" for a port reserved directly via its own
Reserve button, but the Test Name column stays "—" for that kind of
plain reservation. Test Name only populates once a testbed is actually
activated.

UI update (2026-09-17): under this account's default "Automatic"
Activation Mode preference (User menu -> Preferences -> Activation Mode),
the old separate Apply ("Save & activate") step no longer exists — a
single "Start" button now activates AND runs traffic together (behind a
"Testbed is Inactive" confirmation modal). So, unlike before, this test
can no longer inspect an activated-but-not-yet-running state: some
traffic now runs briefly as an unavoidable side effect of activating.
That doesn't affect what's actually being asserted here (Reserved By /
Test Name reflect activation, not run state), so the test still doesn't
need to wait for a run to finish — it just can't claim "no traffic is
ever generated" as a resource-usage guarantee like it used to.

REWRITTEN 2026-10-11 on pages/ (5.0.9): an active testbed's ports read
Status "Active" (not 4.0's "Reserved"), Reserved By the account, and Test
Name the testbed.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from pages import PortSpec, StreamSpec, TestbedSpec, settings

NAME = "T3-ActiveCols"
SPEC = TestbedSpec(ports={1: PortSpec(rate=1), 2: PortSpec(rate=1)},
                   streams=[StreamSpec("UDP")], duration_s=20)


@pytest.mark.stateful
def test_t3_reserved_by_and_test_name_populate_on_activation(dashboard: Page, traffic_engine):
    board = traffic_engine.dashboard
    for port in SPEC.port_numbers:
        expect(board.port_row(port).get_by_text("Unreserved", exact=True)).to_be_visible()

    traffic_engine.create(NAME, SPEC)
    traffic_engine.start(NAME)
    board.open()
    for port in SPEC.port_numbers:
        row = board.port_row(port)
        expect(row.get_by_text(re.compile(r"^(Active|Reserved)$"))).to_be_visible()
        expect(row).to_contain_text(settings.NTG_USER)
        expect(row).to_contain_text(NAME)

"""xfail markers for confirmed product bugs (netropy-ui-findings.md), in one
place. Non-strict: a fixed bug shows up as XPASS, not as a failure, and the
marker (and the finding) should then be retired."""
import pytest

LIVE_RUN_INTERRUPTED = pytest.mark.xfail(
    strict=False,
    reason=(
        "Finding 'Any backend write while a run is live can silently interrupt it' "
        "(2026-09-15/17, 5.0.7): editing+saving a live testbed, cloning it, or creating and "
        "deleting an unrelated draft each ended the live run within seconds, and the saved "
        "run lost its result. Not yet re-checked on 5.0.9."
    ),
)

RESTART_ENDS_EARLY = pytest.mark.xfail(
    strict=False,
    reason=(
        "Finding 'Restarting Start after Stop can silently end a run in a few seconds' "
        "(2 observations, 4.0/5.0.7). Not yet re-checked on 5.0.9."
    ),
)

DOUBLE_CLICK_STATS_STUCK = pytest.mark.xfail(
    strict=False,
    reason=(
        "Finding 'Start double-click can leave a completed run's Stats view stuck on "
        "\"never started\"' (one observation, 2026-09-15). Not yet re-checked on 5.0.9."
    ),
)

VXLAN_START_IDLE = pytest.mark.xfail(
    strict=False,
    reason=(
        "Finding 'VXLAN: activation succeeds but Start intermittently never begins traffic' "
        "(start returns traffic-running true with datapath IDLE; 2 of 3 runs, 2026-09-10; also "
        "seen in an ARP+DNS+VXLAN mix 2026-09-15)."
    ),
)

PORT_CONFLICT_SILENT = pytest.mark.xfail(
    strict=False,
    reason=(
        "Finding (test_t10_port_conflict_while_active, 2026-09-15): a second testbed claiming a "
        "live testbed's ports failed silently with no visible error. 5.0 auto mode may now "
        "handle this differently; re-checked by this test."
    ),
)

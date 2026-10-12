# `pages/`: the shared test library

Every selector for the NTG and the WAN emulator lives here. When the UI
changes, fix it here once, run `pytest tests/t0_library` to confirm, and
every test picks it up.

## Add a traffic test (the usual case)

```python
import pytest
from pages import PortSpec, StreamSpec, TestbedSpec

SPEC = TestbedSpec(
    ports={3: PortSpec(rate=1, ip="10.0.30.1", cidr=29),       # rate in Gbps unless unit=
           4: PortSpec(rate=1, ip="10.0.30.2", cidr=29)},      # dst_ip defaults to the peer's ip
    streams=[StreamSpec("UDP", frame_size=1500)],             # Add Stream list label
    duration_s=30,                                            # or ramp=(up, hold, down)
)

@pytest.mark.stateful
def test_t10_my_scenario(traffic_engine):
    traffic_engine.run("T10-MyCase", SPEC).assert_passed()   # name <= 15 chars
```

`traffic_engine.run()` checks that nobody else holds the ports (if someone does, the test is
skipped, never stolen). It then creates and configures the testbed, starts it (a failed start
is diagnosed as a unit crash or an ordinary failure), waits for the saved run, and reads the run
through the API onto the **summary sheet**. `assert_passed()` requires the NTG verdict to be
pass **and** frames to have been sent and received: the NTG says "pass" even when no criteria
are set. Teardown deletes every testbed the test created, and only those.

When a scenario needs to act mid-run (stop, edit, clone, ...), use the pieces directly:
`traffic_engine.create(name, spec)`, `.start(name)`, `traffic_engine.dashboard.*`, then
`traffic_engine.result(name, row)` to record the run. See `tests/t10_t12_lifecycle/`.

Speaker 1's script style also works unchanged:
`CreateTestbedPage(page).create_testbed(...)` … `.start_test(duration)`
(`tests/t10_t12_lifecycle/test_t10_facade_examples.py`).

## What's where

| Module | What it covers |
|---|---|
| `login_page.py` | sign-in (credentials from `.env`) |
| `dashboard_page.py` | Port Status, port ownership (Controller API), testbed tiles: create, edit, start/stop, clone, reports, remove |
| `testbed_editor_page.py` | editor steps 1–4 and the bottom bar (Save / Start) |
| `run_page.py` | Statistics: wait for the saved run, verdict, exports, delete run |
| `unit_health.py` | crash detection: UI top bar + Controller health and datapath state |
| `traffic_engine.py` | `TestbedSpec` → checked, recorded run |
| `testbed_spec.py` | the config block: `TestbedSpec` / `PortSpec` / `StreamSpec` |
| `wan_emulator_page.py` | WAN emulator: delay helper plus a generic path builder keyed by form field `name` (see `docs/wan-emulator-reference.md`) |
| `create_TE_testbed_page.py` | Speaker 1's `CreateTestbedPage` API on top of the above |
| `settings.py`, `errors.py` | `.env` targets; `SystemBadStateError`, `PortsBusyError` |

## Rules
- Selectors only here. Role-based and scoped to a row, tile or modal. No `nth()` on lists of
  testbeds, no CSS chains. Where the UI gives nothing better, use one documented fallback with
  a comment saying why (e.g. the unlabelled Quantity field).
- No `wait_for_timeout` except as a poll interval; every action ends with an `expect()`.
- Set, don't toggle: read a checkbox's state before clicking it.
- Never release, stop or delete anything this test didn't create.

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

## Add a WAN emulator test

```python
from pages.wan_path_spec import Impairment, WanPathSpec

PATH = WanPathSpec("t15-delay", a_to_b=Impairment(delay_ms=50))   # b_to_a defaults to the same

@pytest.mark.stateful
def test_t15_my_case(wan_bench):
    baseline = wan_bench.baseline(TESTBED, SPEC)     # Engine 2 bypass; reused within a session
    run = wan_bench.impaired(TESTBED, SPEC, PATH)    # path applied, run, engine restored
    wan_bench.check_delay(run, baseline, PATH)
    wan_bench.assert_ok()
```

`Impairment` fields, per direction: `delay_ms` (constant delay), `loss_pct` (random loss) and
`bandwidth_mbps` (a cap on the direction's access link, where its queue sits). Each has a check:

| Check | What must hold |
|---|---|
| `check_delay(run, baseline, path)` | latency rises by the delay; no frame arrives early; nothing dropped |
| `check_loss(run, baseline, path)` | NTG loss % = the setting; NTG lost frames = emulator WAN drops; no added latency |
| `check_bandwidth(run, baseline, path)` | cap below the offer: received rate = cap, NTG lost frames = emulator queue drops. Cap above it: nothing lost, full rate, no added latency |
| `check_verdict(run, testbed, max_loss_pct)` | sets the saved run's Max loss criterion in the UI; the verdict follows the measured loss on screen and in the Controller |

Before a test's first run, `wan_preflight.py` checks and sets up the bench: NTG healthy, Ports 3/4
free (or ours), their links up (it waits out a flap) at a speed that covers the spec, Engine 2 idle
(our own leftovers are cleaned up), and no leftover paths of ours. Someone else's Engine 2 setup is
never overwritten while traffic flows through it; when it's idle, tests skip unless `.env` has
`WAN_BORROW_IDLE_ENGINE=true`, in which case it's borrowed and put back at session end. Results go on
the summary sheet as `preflight`.

Every bench run also checks that the UI's Avg Latency card matches the saved run and that both
boxes count the same frames: emulator delivered = NTG received, delivered + dropped = NTG sent. A path that loses frames by design isn't
required to have a "pass" verdict (the NTG's default is loss-based); `check_verdict` tests the
verdict itself. A new kind of impairment goes into `Impairment.fields()`, with a `check_*`
method on `WanBench`.

## What's where

| Module | What it covers |
|---|---|
| `login_page.py` | sign-in (credentials from `.env`) |
| `dashboard_page.py` | Port Status, port ownership (Controller API; a port is ours only if our own testbed holds it, since the login is shared), testbed tiles: create, edit, start/stop, clone, reports, remove |
| `testbed_editor_page.py` | editor steps 1–4 and the bottom bar (Save / Start) |
| `run_page.py` | Statistics: wait for the saved run, verdict, pass criteria (the ⚙ popover), exports, delete run |
| `unit_health.py` | crash detection: UI top bar + Controller health and datapath state |
| `traffic_engine.py` | `TestbedSpec` → checked, recorded run |
| `testbed_spec.py` | the config block: `TestbedSpec` / `PortSpec` / `StreamSpec` |
| `wan_emulator_page.py` | WAN emulator UI: engine state (Emulation, Default Actions), create/delete a path, `applied(spec)` / `path_created(spec)` context managers that always restore the engine (see `docs/wan-emulator-reference.md`) |
| `wan_path_spec.py` | `WanPathSpec` / `Impairment`: a path's config block, per direction; also checks the box's stored path against it |
| `wan_bench.py` | `WanBench` (the `wan_bench` fixture): NTG Port 3 → Engine 2 → Port 4. Baseline vs impaired runs, both boxes' counters on the summary sheet, delay / loss / bandwidth / verdict checks |
| `wan_preflight.py` | pre-run checks and set-up for the bench; `EngineLease` borrows an idle Engine 2 (opt-in) and puts it back |
| `create_TE_testbed_page.py` | Speaker 1's `CreateTestbedPage` API on top of the above |
| `settings.py`, `errors.py` | `.env` targets; `SystemBadStateError`, `PortsBusyError` |

## Rules
- Selectors only here. Role-based and scoped to a row, tile or modal. No `nth()` on lists of
  testbeds, no CSS chains. Where the UI gives nothing better, use one documented fallback with
  a comment saying why (e.g. the unlabelled Quantity field).
- No `wait_for_timeout` except as a poll interval; every action ends with an `expect()`.
- Set, don't toggle: read a checkbox's state before clicking it.
- Never release, stop or delete anything this test didn't create.

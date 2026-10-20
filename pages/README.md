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

`Impairment` fields, per direction:

| Field(s) | Emulator setting |
|---|---|
| `delay_ms` | constant delay |
| `delay_ms` + `jitter_ms` | normal delay: mean, σ (mean ≥ 3σ) |
| `delay_ms` + `delay_max_ms` | uniform delay between the two |
| `allow_reordering` | variable delay may reorder frames (off: delays are skewed to keep order) |
| `loss_pct` | random loss |
| `bandwidth_mbps` | a cap on the direction's access link, where its queue sits |
| `duplicate_pct` | duplication |
| `reorder_pct`, `reorder_offset` | reordering: % of frames, held back by N frames |
| `outage_s`, `outage_every_s` | periodic outage |

Ways to run, besides `baseline` / `impaired`:

| Call | What it does |
|---|---|
| `impaired_with_change(testbed, spec, path, change_to, after_s)` | edits the path (Apply Changes) `after_s` into the run; the edit's timing goes in `run.marks` |
| `routed(testbed, spec, {stream index: path})` | endpoints send each stream (UDP / TCP, matched by protocol, a full port range and the NTG port's IP) through its own path; everything else bypasses |
| `read_preset(group, item, name)` | a built-in preset ("Cellular", "4G LTE") read back as a `WanPathSpec`; fails, naming the setting, if it uses something `Impairment` can't describe |

Each kind of impairment has a check:

| Check | What must hold |
|---|---|
| `check_delay(run, baseline, path)` | latency rises by the delay; no frame arrives early; nothing dropped |
| `check_loss(run, baseline, path)` | NTG loss % = the setting; NTG lost frames = emulator WAN drops; no added latency |
| `check_bandwidth(run, baseline, path)` | cap below the offer: received rate = cap, NTG lost frames = emulator queue drops. Cap above it: nothing lost, full rate, no added latency |
| `check_verdict(run, testbed, max_loss_pct)` | sets the saved run's Max loss criterion in the UI; the verdict follows the measured loss on screen and in the Controller |
| `check_jitter(run, baseline, path)` | latency rises by the mean, none above mean + 6σ or below bypass, jitter rises (its size vs 2σ/√π recorded) |
| `check_sequence(run, path)` | duplicates/reorders: NTG loss never negative, received ≤ sent + duplicates; how the NTG counts them recorded |
| `check_outage(run, path)` | run saved; the per-second receive rate goes dark; NTG lost frames = emulator drops |
| `check_change(run, baseline, before, after)` | per-second latency at the old delay before the edit and the new one after; run saved |
| `check_drain(run, baseline, path)` | run saved; latency rises by the delay; `tail-not-settled` set exactly when frames were in flight |
| `check_preset(run, baseline, path)` | below the preset's caps: its mean delay and loss, frame for frame with the emulator, full rate |
| `check_per_stream(run, baseline, routes)` | each stream's latency and loss show only its own path; the emulator carried it on that path |

Before a test's first run, `wan_preflight.py` checks and sets up the bench: NTG healthy, Ports 3/4
free (or ours), their links up (it waits out a flap) at a speed that covers the spec, Engine 2 idle
(our own leftovers are cleaned up), and no leftover endpoints or paths of ours. Someone else's Engine 2 setup is
never overwritten while traffic flows through it; when it's idle, tests skip unless `.env` has
`WAN_BORROW_IDLE_ENGINE=true`, in which case it's borrowed and put back at session end. Results go on
the summary sheet as `preflight`.

Every bench run also checks that the UI's Avg Latency card matches the saved run and that both
boxes count the same frames: emulator delivered = NTG received, delivered + dropped − duplicated = NTG sent. A path that loses,
duplicates or reorders frames by design isn't required to have a "pass" verdict (the NTG's default is loss-based); `check_verdict` tests the
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
| `wan_emulator_page.py` | WAN emulator UI: engine state (Emulation, Default Actions), create / edit / delete a path, create one from a preset, endpoints, and `applied(spec)` / `path_created(spec)` / `routed(paths, endpoints)` context managers that always restore the engine (see `docs/wan-emulator-reference.md`) |
| `wan_path_spec.py` | `WanPathSpec` / `Impairment`: a path's config block, per direction; checks the box's stored path against it and reads a stored path (a preset) back into a spec. `EndpointSpec` for per-stream routing |
| `wan_bench.py` | `WanBench` (the `wan_bench` fixture): NTG Port 3 → Engine 2 → Port 4. Baseline vs impaired runs (also: edited mid-run, routed per stream, from a preset), both boxes' counters on the summary sheet, a check per impairment |
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

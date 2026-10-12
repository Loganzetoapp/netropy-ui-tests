# Shared test library (`pages/`): current state and implementation plan

**Owner:** Logan · **Written:** 2026-10-11 · **Status:** proposal. The open questions in §6 need answers from Speaker 1 / Travis.

**Target:** NTG `http://192.168.173.212` (health ok; the box was updated around Oct 9).
WAN emulator `http://192.168.173.213`. Speaker 1's drop: `pages.zip` (`login_page.py`,
`create_TE_testbed_page.py`) and `t15_tests.zip` (4 example tests).

---

## 1. What works today (measured 2026-10-11, not assumed)

### Hardware-free: 68 / 71 pass on .212

Run: `pytest -m hardware_free` in 3 min 47 s, history `20261012T043839Z`.

| Failing test | Cause |
|---|---|
| `t7_deleting_all_streams_disables_apply` | New-build copy. The Streams hint now reads "The traffic flows this testbed sends. At least one is needed to activate" instead of "0 streams". |
| `t8_ramp_disabled_by_default` | The Load Profile was redesigned. It now reads "Disabled \| Runs until Manual Stop" and has a mode picker (Manual Stop / …). |
| `t8_ramp_math_updates_total_run_time` | Same redesign: the old "Disabled — traffic runs at full rate" toggle is gone. |

All three are test maintenance, not product bugs.

### Stateful: none currently verified to work on this build

| Group | Tests | State |
|---|---|---|
| Converted to the 5.0 flow (use conftest helpers) | 8 lifecycle, stop/deactivate/rapid-restart, live view, default addressing, fail path, T14 ×2, T15 | **Broken on today's build**: `set_addressing()` (subnet dropdown) and `set_ramp()` (Load Profile redesign) both fail. Confirmed with a probe on a draft testbed that touched no ports. |
| Still on the 4.0 flow (never converted) | asymmetric_subnet, clone_while_active, cross_layer, double_click, edit_config, port_conflict, two_testbeds, unrelated_action, multistream_udp_tcp_100mbps, multistream_tcp_icmp_2gbps, T12 run history, T3 reserved_by_test_name | **Cannot pass.** Each expects "Available" (now "Unreserved"), clicks Apply, or Reserves manually. 14–21 positional `nth()` selectors each, 300–660 lines each. |
| T3 reserve/release ×5 | | Passed on .89 on 10-01. Never run on .212. |
| T15 delay-only | | Passed on .212 on 10-07, before the box update. Uses `set_ramp`/`set_addressing`, so it is now broken too. |

### Other facts that shape the plan
- **The 5.0 migration is uncommitted:** 45 modified files on `wan-emulator-t15`. It has to be committed before any refactor so we have a clean base to diff against.
- **Someone else is using the box.** Ports 3/4 are ACTIVE, reserved by `admin` on testbed "TE" (probably Speaker 1's). All 8 links show Up on .212. Ports 1/2 are 10G; the cabling for 1/2 is unconfirmed.
- **The duplication is real.** Across test files there are 34 copies of `_tile`/`_delete_if_present`, 30 of `_cleanup_from_wherever`, 15 of `_create_and_open_streams`/`_add_stream`, 10 of `_release_ports`, and so on. The `*_all.py` files in T1/T2/T3 duplicate their single-test files outright.
- **The meeting diagnosis holds.** When the build changed, `set_ramp` broke in *one* place (conftest). But ~50 private `_helper` copies and the 11 un-converted tests each break separately.

## 2. Assessment of Speaker 1's library

**Keep (this is the right shape):**
- A test is a **config block plus ~10 library calls**: ports, directions, line rates, per-port network dict, stream list, duration. Readable by someone who has never seen Playwright.
- Method names: `create_testbed`, `ensure_ports_reserved`, `edit_testbed`, `port_config`, `port_line_rate_config`, `network_config`, `stream_config`, `load_profile_config`, `start_test`, `cleanup_testbed`. We keep these as the public API so their scripts keep working.
- Masks selected by value (`"30"`) match the new build. Ours (`label="/24"`) no longer do.
- Card/table-agnostic `testbed_entry()` and the auto-accept for native dialogs.

**Must fix before it runs in this suite:**

| # | Problem | Risk |
|---|---|---|
| 1 | `from config import page` — module not in the zip; compiled files show more missing files (`create_testbed_page`, `t10_asymmetric_subnet_page`) | won't import |
| 2 | `release_port()` clicks Release, then "Deactivate & release", on any port that shows a Release button. It is called at the *start* of every test. | **On a shared box, this stops someone else's run.** Today it would kill testbed "TE" on 3/4. |
| 3 | Every test uses the testbed name `"TE-Test"`; `delete_if_exists` deletes it unconditionally | collides with and deletes other people's work |
| 4 | Credentials `test`/`test` and URL `.212` hardcoded | violates CLAUDE.md; `.env` already has them |
| 5 | `start_test()` sleeps for duration + 50 s and never checks the verdict | **a test passes even if traffic never starts** — exactly the "failed before start" case from the meeting |
| 6 | Fixed sleeps throughout (5 s before every delete and every load profile) | slow *and* still flaky |
| 7 | `network_config()` falls back to `nth(2)` and a 6-level CSS `nth-child` chain | the breakage the library is meant to prevent |
| 8 | Toggles are clicked, not set (`port_config`, `load_profile_config`) | already-on becomes off |
| 9 | `t15_tests/conftest.py` replaces the authenticated `page` with a blank one | skips the session login, card-view pin and screenshots; the dashboard can't see these tests properly |
| 10 | All 4 tests are named `test_main`; two use ports 1/2 | naming convention; cabling unknown |

## 3. Target design

```
pages/                         ← repo root, as decided in the meeting
  __init__.py                  exports the classes below
  base_page.py                 BasePage: page, toasts(), go_home(), wait helpers (expect only, no sleeps)
  login_page.py                LoginPage.login() — reads .env; used by the session fixture AND T1 tests
  dashboard_page.py            DashboardPage: port_row(n), port_owner(n), testbed_entry(name),
                               create_testbed(), delete_testbed(), reserve/release (ownership-checked)
  testbed_editor_page.py       TestbedEditorPage: step(n) open/locked state, ports step, network step,
                               streams step, load-profile step, save/discard/start
  run_page.py                  RunPage (Statistics): wait_for_run_to_finish, verdict, run row, stop
  unit_health.py               UnitHealth: UI top bar + read-only API status → SystemBadStateError
  wan_emulator_page.py         wan_emulator.py moved into a page class (single page)
  create_TE_testbed_page.py    CreateTestbedPage — Speaker 1's public API, now a thin facade
                               over the classes above (keeps their scripts/method names working)
  testbed_spec.py              TestbedSpec / PortSpec / StreamSpec dataclasses (the "config block")
```

**Ground rules for the library** (CLAUDE.md, plus lessons from the last month):
1. **Selectors live only in `pages/`.** Tests never call `page.get_by_*`, except for a test's own one-off assertion. Every selector is role-based and scoped to a row, card or step; no `nth()` on lists; no CSS chains. Where no stable hook exists, use one documented fallback with a `# needs data-testid` comment, and collect these for the data-testid ask.
2. **No `wait_for_timeout`.** Every action ends with an `expect()` on its result: the toggle is checked, the value committed, the tile gone.
3. **Set, don't toggle.** `set_port_enabled(n, True)` reads the state first.
4. **Never touch what we don't own.** `DashboardPage.port_owner(n)` reads Reserved-by/Test-name. Release only if the port is ours *and* on our testbed. If it's held by anyone else, **skip the test** with "Port 3 in use by 'TE' (admin)"; never release. Only delete testbeds whose name this test generated.
5. **Unique, valid names.** The `testbed_name` fixture builds `<area>-<short-hash>` and asserts ≤15 chars (the 502-on-activate bug).
6. **Fail loud and classified.** Start → if traffic is not running within the timeout, `UnitHealth.diagnose()` decides: unit/controller unhealthy or datapath ERROR → `SystemBadStateError` (system failure); healthy → ordinary failure with toasts and testbed status in the message.

**What a test looks like afterwards** (Speaker 1's style, our safety):

```python
SPEC = TestbedSpec(
    ports={3: PortSpec("bidirectional", rate_gbps=1, ip="30.20.20.2", mask=30, dst="40.0.0.12"),
           4: PortSpec("bidirectional", rate_gbps=1, ip="40.0.0.12", mask=29, dst="30.20.20.2")},
    streams=[StreamSpec("UDP", frame_size=1500)],
    duration_s=10,
)

@pytest.mark.stateful
def test_t10_udp_1500_ports_3_4(traffic_engine):        # fixture: logged-in, ports checked, auto-cleanup
    run = traffic_engine.run(SPEC)                      # build → start → wait → verdict + metrics
    assert run.verdict == "pass", run.summary_text
```

**Fixtures (conftest.py):** `dashboard_page`, `editor`, `testbed_name`, and `traffic_engine`. `traffic_engine` creates the testbed, checks port ownership, tears down only its own testbed, and records metrics. The existing session auth, screenshots and history hooks stay unchanged.

**Summary page on every test:** `RunPage.finish()` reads the saved run via `ntg_api` (read-only, `/runs`; never live `/stats` on a stopped test) and feeds the `run_metrics` fixture. Every stateful test then gets the measurements section T15 has, without per-test code.

**Crash detection:** `UnitHealth` combines the UI top bar (online/offline/RECOVERY), `ntg_api.health()`, and `ntg_api.datapath_state(name)` (status only). When Speaker 1 sends the testbed-status command, it is added here, in one place. A screenshot is already captured on failure. Claude's screenshot review stays in the dashboard's failure-review step, not in the test.

## 4. Implementation phases

Each phase ends with a gate. Nothing stateful runs without Logan's explicit go-ahead and a free box.

| Phase | Work | Gate |
|---|---|---|
| **0. Baseline** | Commit the pending 5.0 migration as-is. Get Speaker 1's missing files. Confirm the account (`test` vs `admin`) and which port pairs are cabled on .212. | clean `git status`; answers to §6 |
| **1. Library core** (hardware-free) | Build `pages/` per §3. Port the *working* logic from `conftest.py` (`start_testbed`, `wait_for_run_to_finish`, `remove_testbed`, health). Fix the new-build selectors: mask by value, the new Load Profile mode picker, the step tabs. Wrap Speaker 1's API as the facade. | **Library self-tests**: a new `tests/t0_library/` (hardware_free). Each page method runs once on a draft testbed (enable ports, set addressing, add streams, set load profile, save, discard, delete) with no reservation and no traffic. 3 consecutive passes. |
| **2. Switch conftest to the library** | The conftest helpers become one-line shims calling `pages/`, so all existing tests go through the library immediately. Fix the 3 hardware-free failures. | `pytest -m hardware_free` 71/71, 3× back-to-back (stability run) |
| **3. Migrate hardware-free tests** | One area at a time (T4 → T9): delete each file's private `_helpers`, call `pages/`. Remove the duplicate `*_all.py` files in T1–T3, if Travis agrees. | each area: 3 consecutive passes; net line count down |
| **4. Stateful, one golden test first** ⚠ needs go-ahead | Speaker 1's `test_udp_1500` rewritten on the library, ports 3/4, 1 Gbps, 10 s. It proves create → start → verdict → cleanup → metrics on the real box. | 3 consecutive passes; box left clean (no testbeds, ports free) |
| **5. Stateful, the rest** ⚠ | Lifecycle 8 → stop/deactivate/rapid → T14 → T15 → Speaker 1's 3 other examples. Then the 11 unconverted 4.0 tests, each rewritten on the library *or* retired if it duplicates another. | per test: 3 passes, or a reported product bug |
| **6. Crash detection and summary everywhere** | `UnitHealth` wired into `start`/`finish`; metrics for every stateful test. Plug in Speaker 1's status command when it arrives. | a forced failed start is recorded as `failure_kind=system` |
| **7. Handoff** | `pages/README.md` (how to add a testbed in ~20 lines), a CLAUDE.md rule ("new tests use `pages/`; no selectors in tests"), and code sent back to Speaker 1. | Speaker 1 / Mike can add a test without reading Playwright docs |

**Order rationale:** hardware-free first, because it is safe anytime and exercises ~80% of the same editor code. One golden stateful test before the rest, because every stateful failure costs a box cycle on shared hardware.

## 5. Risks

- **The build changes under us again.** Mitigation: the t0 library self-tests run first in every suite run, so a UI change shows up as "library: set_load_profile broken" instead of 30 unrelated failures.
- **Shared box contention.** Mitigation: the ownership check skips, never steals. Stateful runs happen only when the box is confirmed free.
- **The facade drifts from Speaker 1's copy.** Agree that the repo copy is the source of truth after Phase 1.
- **The new Load Profile mode picker** (Manual Stop / timed / ramp) is not yet mapped. Phase 1 starts by recording it.

## 6. Open questions (Speaker 1 / Travis)

1. Send `config.py`, `create_testbed_page.py` and `t10_asymmetric_subnet_page.py`. Are there others?
2. Which account should the suite use, `test` or `admin`? The box is currently held by `admin` on "TE".
3. Which port pairs are cabled on .212? Is 3/4 through the WAN emulator and 1/2 back-to-back?
4. Is it OK to split `create_TE_testbed_page.py` into dashboard / editor / run pages behind the same public method names?
5. Is it OK to delete the duplicate `*_all.py` tests in T1–T3?
6. The testbed-status command for crash detection (it takes a test ID).

## 7. UI notes found during this investigation (to report)

- In the Network step's table view, the subnet column header is just "/" and its dropdown has no accessible name, so screen readers announce nothing useful. (It's also why the selector is hard to write without position.)
- ~~No version visible~~. Correction: Menu → Settings shows "Version 5.0.9", and `/system` returns it. The suite now records it per run.
- Correction to §1: `set_addressing` is **not** broken. The CIDR select offers only /25–/32, and my probe passed /24. Only `set_ramp` is broken on 5.0.9 (the Load Profile text changed).

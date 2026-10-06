# WAN emulator + traffic generator: test and results plan

**Owner:** Logan · **Written:** 2026-10-05 · **Status:** proposal, needs Travis's input on the decisions in §7

**Lab pair:** traffic generator (NTG) `http://192.168.173.212`, WAN emulator
`http://192.168.173.213` (Netropy 10G2, firmware 5.1.5). The NTG's Port 3 ⇄
Port 4 run through emulator **Engine 2** (emulator ports 3/4).

**Where we are:** T15 (delay only) passes. With 50 ms set on the emulator,
the NTG's average latency goes from 0.223 ms to 50.223 ms. The plumbing
works. This plan covers what to test next, how to make results say more
than pass/fail, and how to get live data onto the dashboard.

---

## 1. Why test through the WAN emulator

On its own the NTG only shows how it behaves on a perfect cable: no loss,
no delay, and full line rate. Putting the emulator in between turns every
run into a **known-answer test**. We set exactly what the network does
(50 ms delay, 1 % loss, a 100 Mbps cap), and the NTG has to report it back.
That covers three things the cable-only suite can't:

1. **Measurement accuracy.** Are the NTG's latency, jitter, loss and
   throughput numbers right? Today nothing checks them. A run "passes" if it
   didn't fail.
2. **Pass/fail verdicts.** Does the NTG fail a run when it should? Its
   criteria (max loss %, max latency µs, min Rx % of line rate) can only be
   exercised by a network that actually breaks them.
3. **Robustness under bad networks.** ARP through a lossy link, long delays
   that outlast the run's drain window, outages mid-run, duplicated or
   reordered frames. These are the conditions most likely to reproduce the
   "bad state" and lost-run bugs (findings #1/#2), and customers' networks
   produce them.

**The key idea: two independent witnesses.** The emulator counts what it
*did* to every frame (dropped, duplicated, reordered, corrupted, queued).
The NTG counts what it *saw* (lost, latency, jitter). The two counts should
agree, and when they don't, one of the boxes has a bug. Example: with
random loss on, the NTG's lost-frame count should equal the emulator's
`wan-drops` for that direction, give or take frames still in flight at the
end of the run.

---

## 2. What each box reports

### WAN emulator (per path, per direction a→b / b→a)
Source: the YANG model embedded in the emulator UI (`apposite-statistics`).
Read with `POST /api/apposite-netropy-device:get-stats-summary` (totals) and
`get-stats-records` (per-second series, by metric).

| Group | Fields | What it tells us |
|---|---|---|
| Overall | rate, frames, bytes, drops | Traffic that entered the path. a→b frames should equal NTG Port 3's TX, which also proves the cabling and direction mapping |
| WAN impairment | drops, duplicates, reorders, corruptions | What the emulator did on purpose. The NTG's loss, out-of-order and FCS-error counts should match these |
| Inflow / outflow access link | rate, frames, bytes; queue frames/bytes/**length**/**drops**; background frames/bytes/drops | Bandwidth-cap behaviour: queue build-up (adds latency) and tail drops (adds loss) |
| Engine status | emulation on/off, buffers free/**failures**, log | Emulator health. Buffer failures mean the emulator itself dropped frames, which would make a test fail for the wrong reason |

The emulator **does not measure latency**. It applies it. Latency is only
measured by the NTG.

### Traffic generator (`/ctrl/v1`, OpenAPI at `/ctrl/v1/openapi.json`)
| Endpoint | Gives |
|---|---|
| `GET /tests/{name}/status` | Lifecycle truth: datapath state (LEARNING / RUNNING / ERROR) |
| `GET /tests/{name}/stats?streams=1&since=<s>` | Live view, ~1 Hz. Summary (tx/rx rate, loss frames/%, avg/min/max latency, avg/max jitter, cur-* for the newest window), **per port**, **per stream**, **per direction** (from-port → to-port), per-second `sample[]`, NIC counters (`nic-rx-errors`, `rx-missed`, `rx-no-mbuf`), and an `event[]` log |
| `GET /tests/{name}/runs`, `/runs/{id}/summary`, `/runs/{id}/stages` | Saved run: final numbers, phase timings (setup / ramp / main / tail), `end-reason`, `tail-not-settled` |
| `GET/POST …/criteria`, `set-run-criteria` | The NTG's own pass/fail rules: max loss %, max latency µs, min Rx % |
| `GET /health`, `/system` | Unit health (already used by the bad-state check) |

**Safety rule, from the engineer's notes:** never poll `/stats` on a stopped
test until `/runs` shows the new run record, because it can crash the
Controller. Every poller below has to check `status` and `runs` first.

---

## 3. Ways to use the WAN emulator

From the emulator's own model and UI, roughly from simplest to most realistic:

| # | Method | How | Use it for |
|---|---|---|---|
| A | **Default Action → one path** *(what T15 does)* | Both ports' Default Action = the path; Emulation on | Everything between Port 3 and 4 gets the same impairment. Simple; no classification to get wrong |
| B | **Asymmetric path** | Different settings per direction in one path (Port 3→4 vs 4→3) | Real links are asymmetric (e.g. a 25/3 Mbps satellite link). Checks that the NTG reports each direction separately (`flow[].direction[]`) |
| C | **Endpoints + rules → several paths** | Endpoints match on port / VLAN / IP / TCP-UDP port; rules map endpoint pairs to paths | Different impairment per stream in one run, e.g. the UDP stream gets 1 % loss and the TCP stream gets 50 ms. Checks the NTG's per-stream stats attribute correctly |
| D | **Built-in presets** | Path editor's preset menu: 3G / 4G LTE / 5G, Wi-Fi a/b/g/n/ac, satellite LEO/MEO/GEO, cloud region pairs, T1/T3/VDSL | "Realistic network" scenarios: bandwidth + delay + jitter + loss as a bundle. Good golden-suite cases: easy to explain, easy to compare across releases |
| E | **Distribution models** | Delay: constant / uniform / exponential / normal / accumulate-burst. Loss: random / burst / periodic / Gilbert-Elliot / BER. Also outage, corruption, reordering, duplication, IP mangle | Accuracy tests for jitter and loss patterns, plus edge cases the NTG may mishandle (duplicates, reordering) |
| F | **Access-link shaping** | Bandwidth cap, background utilisation, queue limit (drop-tail / RED), queue strategy (FIFO / priority / round-robin), MTU limit, frame overhead | Throughput accuracy, and what happens when the NTG offers more than the link carries (queue delay + tail drop) |
| G | **Change it mid-run** | Edit the path (Apply Changes) while traffic runs | Time-varying networks: does the NTG's per-second graph show the step change at the right moment, and does the run survive it? |
| H | **Playback recordings** | Path "Playback" replays a recorded network-condition trace | Most realistic, but needs recordings. Later |
| I | **Engine 1** | Same, on emulator ports 1/2 | Only if NTG ports 1/2 get cabled through it; Engine 1 shows only 14 frames ever on .213, so it isn't cabled now |

**Recommendation:** build on A first (done). Add B and F next (cheap, high
value), then E and G. C, D and H after the results work in §5 exists,
because their value is in comparing many numbers at once.

---

## 4. New tests, in priority order

Each test follows the T15 pattern: a baseline run with the emulator in
pass-through, then the impaired run, then compare. All are `stateful`,
run on Port 3 ⇄ 4, and stay ≤ 500 Mbps per port (the emulator's Port 4
link is 1G).

| ID | Test | Configure | Assert (NTG ↔ emulator) | Why it matters |
|---|---|---|---|---|
| T15a ✅ | Delay only | 50 ms constant, both directions | avg latency +50 ± 5 ms; loss 0 | Done |
| T15b | **Delay sweep** | 1, 10, 100, 500 ms | Rise matches each setting; min ≈ max for constant delay | Linearity / unit errors (µs vs ms) |
| T15c | **Asymmetric delay** | 10 ms 3→4, 80 ms 4→3 | Per-direction latency matches each side | Per-direction reporting |
| T16a | **Random loss** | 1 % and 5 % | NTG `loss-pct` ≈ setting; **NTG loss-frames == emulator wan-drops** (± in-flight) | Loss accuracy + cross-box accounting |
| T16b | **Loss vs NTG criteria** | 2 % loss, criterion max-loss 1 % | NTG verdict = FAIL; with criterion 5 % → PASS | The NTG's pass/fail logic |
| T17a | **Bandwidth cap** | 100 Mbps cap, offer 500 Mbps | NTG rx-rate ≈ 100 Mbps; loss ≈ 80 %; emulator queue drops ≈ NTG loss | Throughput accuracy, overload behaviour |
| T17b | **Cap with headroom** | 400 Mbps cap, offer 300 Mbps | Zero loss; latency rises only by queueing | Shaper doesn't add false loss |
| T18a | **Jitter** | Normal delay mean 20 ms, σ 5 ms | NTG avg jitter in the expected range; min/max latency within bounds | Jitter accuracy |
| T18b | **Duplication / reordering** | 1 % each | Run completes; NTG doesn't report negative loss or > 100 % rx; note how it counts them | Likely bug area: unusual accounting |
| T19a | **Outage mid-run** | Periodic outage (e.g. 2 s every 10 s) | NTG per-second `sample[]` shows gaps at the right times; the run is saved, not lost | Robustness + the crash/bad-state check |
| T19b | **Change mid-run** | Start at 10 ms, switch to 100 ms halfway | Per-second latency steps at the switch time | Time-series correctness |
| T19c | **Long delay vs drain** | 2 s delay, short run | Run is saved; `tail-not-settled` reported honestly; no lost run | Edge of the drain window; overlaps finding #1 |
| T20 | **Presets** (golden set) | LTE, GEO satellite, 802.11n | Each within tolerance on rate / latency / loss | Release-to-release regression |
| T21 | **Per-stream paths** (method C) | UDP stream → loss path, TCP stream → delay path | Each stream shows only its own impairment | Per-stream attribution |

**Golden overnight candidates:** T15a, T16a, T17a, T19a, plus one preset.
Together they cover delay, loss, rate, robustness and a realistic bundle in
about 15 minutes.

---

## 5. Better results: measured numbers, not only pass/fail

Today a history file stores `outcome`, `duration`, failure message and
screenshot per test. A WAN run should also keep **what was configured,
what each box measured, and whether they agreed**.

### 5.1 Capture (per test)
- A `wan_metrics` fixture that tests fill in, stored on
  `item.user_properties` so it travels to the history writer. This also
  replaces `record_property` and its xunit2 warning.
- Shape (one entry per run inside the test, e.g. baseline and impaired):

```json
"metrics": {
  "impairment": {"engine": 2, "path": "t16-loss", "a-to-b": {"loss": "random 1%"}, "b-to-a": {...}},
  "runs": [{
    "label": "impaired",
    "ntg": {"summary": {...}, "direction": [...], "flow": [...], "stages": {...}, "end-reason": "..."},
    "wan": {"a-to-b": {"frames": ..., "wan": {"drops": ...}, "inflow": {...}}, "b-to-a": {...}, "buffers": {"failures": ...}},
    "series": {"ntg": "<sample[] per second>", "wan": "<get-stats-records per second>"}
  }],
  "checks": [{"name": "loss-pct", "expected": 1.0, "measured": 0.98, "tolerance": 0.2, "ok": true},
             {"name": "ntg-lost == wan-drops", "expected": 9012, "measured": 9010, "ok": true}]
}
```

- `scripts/collect_run.py` copies `metrics` into `results/history/<run>.json`.
  Per-second series can be large, so store them in a sidecar
  (`results/series/<run>/<test>.json`) and link to it.

### 5.2 Results page (dashboard run detail + `results/index.html`)
For each WAN test:
1. **Expected vs measured table.** One row per check, with tolerance, the
   delta and ✅/❌. This is what Travis reads first.
2. **Two-witness panel.** NTG vs emulator side by side: frames in/out,
   drops, duplicates, per direction, with any mismatch highlighted.
3. **Time-series charts.** NTG latency, rate and loss per second, overlaid
   with the emulator's per-second rate and drops, so an outage or a mid-run
   change is visible at a glance.
4. **Run phases.** setup / ramp / main / tail from `stages`, plus
   `end-reason` and `tail-not-settled`.
5. **Health.** Emulator buffer failures and log, NTG `/health` and NIC
   errors. A failure caused by the lab, not the product, says so (feeds the
   existing SYSTEM-failure pill).
6. **Trend across runs.** The same check over the last N runs (e.g. latency
   error drifting after a firmware upgrade), using the existing history
   charts.

---

## 6. Live dashboard: pulling from both APIs during a run

### Design
- **Server-side poller** in the webapp (not the browser): one async task per
  running test, started when the runner launches a `stateful` test, stopped
  when it ends. The browser never talks to the lab boxes directly. That
  keeps credentials off the page and gives one poll stream however many
  people are watching.
- **Push to the browser over the existing SSE channel**
  (`/api/runs/{batch}/stream`). It already streams test progress; add a
  `live-stats` event type.
- **Poll loop (1 Hz):**
  1. NTG `GET /tests/{name}/status`. Only when `datapath-state == RUNNING`:
  2. NTG `GET /tests/{name}/stats?streams=1&since=<last at>` (incremental, so each poll is small)
  3. Emulator `get-stats-summary` for Engine 2's active path(s)
  4. After stop: wait for `/runs` to show the new record **before** any
     further `/stats` call (the Controller-crash rule).
- **How the poller finds the test:** the test publishes `{ntg_test_name,
  emulator_engine, path}` to a small run-state file (or the existing
  per-batch state) when it starts traffic. The poller reads it, so it needs
  no knowledge of each test.
- **Live panel:** current rate, loss %, latency and jitter (NTG), with
  emulator drops/queue per direction beside them, small rolling charts, and
  a status line (LEARNING → RUNNING → saved / LOST / ERROR) from the
  crash-check logic.

### Auth
- NTG: `POST /ctrl/v1/login` once, then a session cookie. For a long-lived
  server, the NTG can mint a persistent **API token** (`POST /api-tokens`),
  which is better than storing a password. Keep it in `.env`.
- Emulator: `POST /login` form, then the `X-Apposite-Netropy` cookie; re-login on 401.
- Both read-only in the poller: GETs and the two `get-stats-*` RPCs only.

---

## 7. Decisions needed (Travis)

1. **API use.** The suite's settled rule is "UI only, never the API". The
   9/30 meeting already reopened it for status checks. Proposal: the **UI
   stays the way tests drive the NTG** (it's what we test); the **API is
   used read-only** for stats, cross-checks and the live dashboard. OK?
2. **Configure the emulator through its UI or its API?** The emulator is
   test infrastructure here, not the product under test, and its UI saves
   asynchronously with no feedback (two quick changes lose one). The API
   would be faster and more reliable. Recommendation: API for setup and
   teardown, plus one separate UI test of the emulator's path editor.
3. **Tolerances.** Proposed starting points, to tune from real data: latency
   ±5 % or ±0.5 ms, whichever is larger; loss ±0.2 percentage points;
   throughput ±2 %.
4. **Dedicated pair?** Is .212/.213 ours for overnight runs, or shared?
   Overnight WAN runs reconfigure Engine 2.
5. **Cabling.** NTG ports 1/2 through emulator Engine 1 would allow two
   independent WAN links (and method I).

---

## 8. Implementation order

| Step | What | Size | Depends on |
|---|---|---|---|
| 0 ✅ | Commit T15 on a branch (`wan-emulator-t15`, 18a28ec). The 3× stability runs were skipped at Logan's request. a→b vs NTG Port 3→4 mapping is confirmed in step 2: a→b = NTG Port 3→4 | S | — |
| 1 ✅ | `ntg_api.py` + `wan_api.py`: read-only clients (login, status, stats, runs, stats-summary/records) with the `/stats`-after-stop guard. Checked against .212/.213 (reads only) | S | Decision 1 |
| 2 ✅ | `run_metrics` fixture (`run_metrics.py`) + history `metrics` + sidecar in `results/metrics/`; T15 records NTG run + config and emulator counters + series. First result: NTG Port 4 sends 1/10 of its rate while the run PASSes | M | 1 |
| 3 | Results page: expected-vs-measured table, two-witness panel, time-series charts | M | 2 |
| 4 | T16a/b (loss, criteria) and T17a/b (bandwidth): first tests using the cross-checks | M | 2, decision 3 |
| 5 | Live poller + SSE `live-stats` + live panel | M | 1 |
| 6 | T15b/c, T18, T19: distributions, asymmetry, outage and mid-run change | M | 4 |
| 7 | Golden overnight set + presets (T20) + per-stream paths (T21) | M | 3, 4, decision 4 |

S ≈ a day or less, M ≈ 2–3 days.

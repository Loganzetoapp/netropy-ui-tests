# NTG 5.0 investigation log

A running record of what's been found on the NTG 5.0 unit and what changed
in the UI test suite because of it. Newest entries go at the top of the
**Log** section; the **Status** table is kept current.

- **Unit under test:** `http://192.168.173.89` (NTG10G4, 8 × 10G ports), firmware 5.0.7 → **5.0.7b** (upgraded mid-session, see 2026-09-30 log)
- **Ports used:** Port 3 ⇄ Port 4, the only cabled pair
- **WAN emulator:** `http://192.168.173.213` since 2026-10-05, paired with the NTG at `.212` (Netropy 10G2, firmware 5.1.5; T15 passes there: 0.223 → 50.223 ms; was `.76` on 5.0.14, where T15 was developed; Engine 2 = emulator ports 3/4, between NTG Port 3 ⇄ 4). Delay-only test T15 **passes 4/4**: NTG avg latency 0.224 → 50.223 ms with 50 ms emulator delay
- **Owner:** Logan · **Started:** 2026-09-30 · **Last updated:** 2026-10-01

## Status

| # | Finding | Kind | Status | Evidence |
|---|---|---|---|---|
| 1 | Frame smaller than the stream's real header size → run dies silently, results lost | Product bug | **Confirmed, cause isolated** — ready for the engineer | 9 protocols; exact TCP cut-off 70 B; 0 counter-examples |
| 2 | TCP / HTTP at 64 B "bad state" (Joe's email) | Product bug | **Explained by #1** on 5.0.7b — run lost, unit stays healthy | TCP, TCP/IPv6, HTTP @ 64 B lost; canary passes |
| 3 | Port 4 link speed unstable (10G → 1G → 0 → 1G) | Lab / hardware | Open — **likely cause found 2026-10-01: the WAN emulator's own Port 4 negotiated 1000 Mbps** (its ports 1–3 are at 10G). Needs someone at the rack | port data, 2026-09-30/10-01 |
| 4 | Port 4 sent ~1/10 of its configured rate (once) | Possible product bug | Unconfirmed — seen once | probe run, 2026-09-30 |
| 5 | Only Port 3 ⇄ 4 are cabled; 1⇄2 and 5⇄6 receive nothing | Lab setup | Open — decision pending | DNS run on 1/2: 304 Mbps TX, 0 RX |
| 6 | Old (4.0) tests couldn't start traffic on 5.0 | Test suite | **Resolved** — tests rewritten | probe run + rewritten tests pass |

## Findings in detail

### 1. Frame smaller than the stream's real header size → run lost (product bug)

**One-line summary for the engineer.** On 5.0.7b, if a stream's frame size
is smaller than the headers that stream actually puts on the wire (plus the
4-byte FCS), Start is accepted, the run looks live for a while, then
Statistics falls back to *"LIVE · IDLE — Ready to start traffic. Ports are
armed and idle."* **No run is saved and no error is shown.** The unit stays
healthy — the next run works. The editor accepts any frame size, so nothing
warns the user.

**Evidence** (Port 3 ⇄ 4, 500 Mbps, one stream, 2/15/2 s ramp; "lost" = no
saved run; every "PASS" had 0.000 % loss):

| Protocol | Real minimum (headers + FCS) | Lost at | Saved (PASS) at |
|---|---|---|---|
| UDP | 14 + 20 + 8 + 4 = **46 B** | — | 64 B (2/2) |
| ICMP | 14 + 20 + 8 + 4 = **46 B** | — | 64 B (2/2) |
| ARP | 14 + 28 + 4 = **46 B** | — | 64 B (2/2) |
| UDP / IPv6 | 14 + 40 + 8 + 4 = **66 B** | 64 B (2/2) | 128 B |
| DNS | 14 + 20 + 8 + 12 + query + 4 ≈ **70 B** | 64 B (2/2) | 256 B |
| NTP | 14 + 20 + 8 + 48 + 4 = **94 B** | 90 B (6/6) | 128 B |
| **TCP** | 14 + 20 + **32** + 4 = **70 B** | 64, 66, 68 B | **70**, 72, 80, 96, 128 B |
| TCP / IPv6 | 14 + 40 + 32 + 4 = **90 B** | 64 B | 128 B |
| HTTP | TCP (70 B) + request text | 64 B | 256 B, 1500 B |

TCP's exact cut-off is **70 B**: 68 B is lost, 70 B passes. That matches a
TCP header carrying 12 bytes of options (20 + 12 = 32 B — consistent with a
timestamps option), and explains why TCP @ 64 B is lost even though a bare
20-byte TCP header would fit.

**What to ask the engineer.**
1. Validate frame size against the stream's header size (editor and API),
   or pad/handle short frames in the datapath.
2. Whatever the fix, a run should never end without a saved record and with
   no error — the user currently sees nothing wrong except missing results.
3. Is this a 5.0 regression? On 4.0, NTP at 90 B ran fine (see
   `netropy-ui-findings.md`). The 4.0-era "VXLAN: Start never begins traffic"
   finding showed the same "armed and idle" symptom and may be this bug.

**Tests:** `tests/t14_64b_frame_bad_state/test_t14_frame_size_vs_headers.py`
(too-small vs fits pairs, plus the TCP cut-off sweep) and
`test_t14_64b_frame_protocols.py` (the 64 B sweep). Lost runs are reported
as **system failure**.

### 2. TCP / HTTP at 64 B "bad state" (Joe's email, 2026-09-30)

> "When you create TCP and HTTP streams that have 64-byte frames it puts the
> system in a bad state (UDP streams are ok at 64 bytes). Let's add a TC(s)
> that test a variety of streams with different protocols using 64-byte
> frames." — Joe

**Result on 5.0.7b (2026-10-01):** TCP, TCP/IPv6 and HTTP at 64 B all lose
their run (finding #1 — none of them fit in 64 B: TCP needs 70, TCP/IPv6 90,
HTTP more). **The unit did not end up in a lasting bad state:** health stayed
"online", and the UDP canary straight after passed. So on 5.0.7b, Joe's
"bad state" shows up as the silent run loss of #1, not a broken unit. The
build Joe tested was likely 5.0.7, before the mid-session upgrade to
5.0.7b — worth asking Vlad whether 5.0.7b changed this, and re-running T14
on the next build.

### 3. Port 4 link speed unstable (lab / hardware)

Port 4's reported speed was 10G at the start of 2026-09-30, then 1G, then
**0 M** (link still "up"), then 1G again. While at 1G the Port 3 ⇄ 4 path
tops out around 1.4 Gbps total — a 3 Gbps two-stream test lost 52.5 %.
Ports 3/4 are cabled through the WAN emulator per the 2026-09-30 meeting, so
the cable, SFP or WAN-emulator port are the likely suspects. Needs someone
at the rack. Tests on 3/4 run at ≤ 500 Mbps–1 Gbps meanwhile.

### 4. Port 4 sent ~1/10 of its configured rate (seen once)

First probe run (2026-09-30): both ports saved at 1000 Mbps, but Port 4
transmitted ~80–100 Mbps while Port 3 sent ~1000. The run still said PASS
(no loss), and the headline "Avg TX" figure hid it — only the Per-Port table
showed it. Not reproduced since; may be the same link problem as #3.

### 5. Only Port 3 ⇄ 4 are cabled (lab setup)

Runs on Port 1 ⇄ 2 and 5 ⇄ 6 transmit but receive nothing (e.g. DNS on 1/2:
304 Mbps sent, 0.0 received, 100 % loss → FAIL). Decision pending: move
every test to 3/4 at ≤ 1 Gbps, or cable 1⇄2 and 5⇄6.

### 6. Why the old tests wouldn't start traffic (resolved)

The unit started traffic fine (a probe run passed). The 4.0 tests broke on
5.0's changed screens before ever reaching Start: 28 of 29 first expected
Port 3 to say "Available" (5.0 says "Unreserved"), and 24 clicked Apply and
waited for Deactivate (5.0 replaced both with Start + the "Testbed is
Inactive" popup).

## Updates to the UI test suite

**Pointing at 5.0**
- `.env` / `.env.example` → `http://192.168.173.89`.
- The dashboard's Run box has a **Target box** picker: the 5.0 unit, the old
  4.0 VM, or a custom IP/URL — sent per run as `NETROPY_URL` and recorded in
  run history.

**Hardware-free tests (71)** — all pass 3 runs in a row on 5.0. Fixes for:
testbed list and Network step defaulting to table view; testbed list
loading after the page; Apply → Start; Iterations field removed; export
JSON now includes the UID; one cleanup that ran from the wrong page.

**Traffic tests** — rebuilt on shared helpers in `conftest.py`
(`create_testbed`, `enable_ports`, `set_addressing`, `add_stream`,
`set_all_frame_sizes`, `set_ramp`, `start_testbed`, `wait_for_run_to_finish`,
`remove_testbed`, …). Converted so far: the 8 lifecycle tests, stop
mid-run, deactivate mid-run, rapid stop/restart, live-view badges, default
addressing, the overload FAIL test, and the T3 port tests. Still to convert:
T12 run history/exports and ~9 longer scenario tests.

**Start popup** — `start_testbed()` handles 5.0's "Testbed is Inactive" →
Continue, and works for dashboard and editor starts.

**System-failure reporting (new)** — per Joe's request to mark these
separately:
- `SystemBadStateError` in `conftest.py`, raised when the unit is unhealthy
  (top bar not "online", or shows "controller offline" / "RECOVERY", or a
  testbed is "disconnected") or when a run is lost.
- Tagged `failure_kind=system` in junit and run history, returned by the
  dashboard API, and shown as a solid red **"system failure"** pill.
- `assert_unit_healthy()` — UI-only health check, used before and after
  each T14 run.
- `wait_for_run_to_finish()` now fails in ~15 s when a run is lost, instead
  of a 3½-minute timeout.

**New test area T14** — `tests/t14_64b_frame_bad_state/` (see #1 and #2).

**Fixed along the way** — the `page` fixture's screenshot/trace logic read
`rep_call`, which nothing set, so every test was treated as failed; a
`pytest_runtest_makereport` hook now sets it.

## Log

### 2026-10-05 — step 2: both boxes' numbers in the run history; Port 4 bug confirmed
- T15 now records, per run, the NTG's saved run and stored config (API) and
  Engine 2's counters and per-second series. Compact numbers go to
  `results/history/`; the full record goes to `results/metrics/` (git-ignored).
  T15 passed 2/2 with it.
- **The emulator's counters are right.** Frame accounting matches exactly in
  every run (902,220 = 902,220 and 90,222 = 90,222), and emulator a→b is NTG
  Port 3→4. The "1/10 b→a" lead was real traffic, not a counting error.
- **Confirmed product bug: NTG Port 4 transmits ~1/10 of its configured rate
  and the run still PASSes with 0 % loss.** Both ports are stored as
  `rate-mbps: 500`. Port 3 sends 465.5 Mbps average (with the 2 s ramps) and
  Port 4 sends **46.5 Mbps** (90,222 vs 902,220 frames), 4/4 runs. Loss only
  compares sent with received, so the shortfall never shows in the verdict.
  Same symptom as finding #4, now measured by two independent boxes.
- **Likely cause (hypothesis, fits the numbers exactly):** the testbed stores
  Port 4 as `speed-mbps: 10000`, the NTG port list reports Port 4 at
  `speed-mbps: 0`, and the emulator port it's cabled to links at 1000 Mbps.
  If the NTG paces a port as a fraction of its nominal 10G (500/10000 = 5 %)
  but the NIC actually runs at 1G, 5 % of 1G = 50 Mbps. To confirm: fix the
  Port 4 link to 10G (cable/SFP/emulator port), or test another rate (e.g.
  200 Mbps should give ~20).

### 2026-10-05 — read-only API clients; two leads from the emulator's counters
- Added `ntg_api.py` and `wan_api.py` (step 1 of docs/wan-integration-plan.md).
  Both only read. The NTG login returns a `session-token` that must be sent
  as a Bearer header (every route except /health answers 401 without it).
  `live_stats()` refuses unless the datapath is RUNNING (Controller-crash rule).
- **Lead, unverified: one direction carried ~1/10 of the frames.** Engine 2's
  Bypass counters on .213 before and after the one T15 run on .212: a→b
  +902,227 frames, b→a only **+90,230**. Only T15's baseline went through
  Bypass (the delayed half used its own path). If each NTG port sent ~902 K
  frames, as on the earlier pair, one NTG port sent about a tenth of its
  share while the run still reported 0 % loss. That's the same symptom as
  finding #4 ("Port 4 sent ~1/10"). Either that bug is back on .212, or the
  emulator's b→a counter is wrong. The next T15 run will settle it once it
  records the NTG per-port TX next to the emulator counts (step 2).
- **Emulator .213 Engine 2 reports 22,267,559,145 buffer failures** (the .76
  unit showed 131.8 M). Not explained yet. Worth asking whether this counter
  means dropped frames, because if so it can corrupt loss results.

### 2026-10-01 (evening) — WAN emulator
- Mapped the emulator at .76 (read-only): Netropy 10G2, 4 ports, 2 engines.
  Engine 1 = ports 1/2, Engine 2 = ports 3/4. Emulation is **off** on both
  (pure bypass), no paths or endpoints. Engine 2 has carried ~264 M / 183 M
  frames each way, which fits NTG Port 3 ⇄ 4 traffic.
- **Emulator Port 4 reports 1000 Mbps, full duplex; ports 1–3 report 10G.**
  That matches NTG Port 4 dropping to 1G (finding #3), so the emulator port,
  SFP or cable on that leg is the prime suspect. Engine 2 also shows 131.8 M
  buffer failures. The emulator log has "redundant power supply failure"
  (Sep 17).
- How to impair NTG traffic: create a path (impairments per direction plus
  an access-link bandwidth per side), point both ports' **Default Action** at
  it, and turn **Emulation** on. No endpoints are needed. A new path's access
  links default to **128 Kbps**, so a delay-only path has to open them up,
  or it throttles the run. The emulator won't delete a path that is still a
  Default Action.
- Wrote `wan_emulator.py`, the `wan_page` fixture and
  `tests/t15_wan_emulator/test_t15_delay_only.py`: a baseline run, then the
  same run with 50 ms each way; asserts PASS and a +50 ± 5 ms rise in NTG
  "Avg Latency". Logan gave permission to drive Engine 2 (ports 3/4).
  **Result: 4/4 passes. Every run: baseline 0.224 ms → 50.223 ms delayed
  (+49.999 ms), 0.000 % loss.** UDP 1500 B, 500 Mbps per port. The NTG
  reports one-way latency per stream, and it matches the emulator setting
  to within 1 µs. Engine 2 is restored to its found state after each run.
- Emulator UI quirks found while automating it (worth reporting):
  - A Default Action change saves **asynchronously, with no feedback**.
    Changing both ports back-to-back silently keeps only one, and
    navigating away within ~1 s silently drops the change. The dropdown
    shows the new value either way. The helper changes one port at a time
    and re-checks after a reload.
  - Path delete is refused while a port still uses the path as its Default
    Action. The refusal is the right behavior, but nothing on screen says
    why it was refused.
  - The emulator's controls have no accessible names (unlabeled selects,
    icon-only links for "+" and the gear), so they can only be selected by
    `name`/`href` attributes.

### 2026-10-01
- **Root cause of the lost runs isolated:** a frame smaller than the
  stream's real header size. TCP cut-off measured exactly: 68 B lost, 70 B
  passes (TCP header carries 12 B of options). TCP/IPv6 @ 128 B and HTTP @
  256/1500 B pass.
- Ran Joe's cases with Logan's go-ahead: TCP, TCP/IPv6, HTTP @ 64 B all
  lose the run; unit stays healthy; canary passes → no lasting bad state on
  5.0.7b.
- Frame-size investigation: 3/3 too-small sizes lost the run, 3/3 sizes that
  fit passed with 0 % loss → finding #1 confirmed and its condition isolated.
- T14 64-byte sweep (UDP, ICMP, ARP, DNS, UDP/IPv6 + canary), twice: UDP,
  ICMP, ARP pass; DNS and UDP/IPv6 lose the run; canary passes (unit healthy).
- Added system-failure reporting end to end (pytest → history → dashboard).
- Lifecycle batch on 5.0: UDP and ARP pass; tests on 1/2 and 5/6 FAIL from
  cabling; 3 Gbps on 3/4 loses 52.5 % (Port 4 at 1G); NTP loses its run 5/5.
- Unit found rebooted and upgraded mid-session: 5.0.7 → **5.0.7b**, uptime
  reset ~20:00 PDT on 2026-09-30.

### 2026-09-30
- Meeting + Joe's email + Abdul's reply: new 5.0 unit, TCP/HTTP 64 B bug,
  crash/status check wanted, dedicated QA unit, Dell switch for future
  GW/checksum tests. Engineer's notes on the status API received (the suite
  stays UI-only; API kept for reference).
- Mapped the 5.0 UI; fixed all 71 hardware-free tests (3/3 runs).
- Added the dashboard target picker.
- Probe run (run by Logan in Terminal, since Claude can't start traffic
  without a permission rule): UDP on 3/4 started and passed → the unit was
  never the reason tests wouldn't start.
- Port 4 rate anomaly (#4) and speed drop (#3) first seen.

# Netropy UI Findings

Everything found while building the automated Playwright suite against the
Traffic Generator web UI — confirmed product behavior, places the written
test plan (`netropy-ui-test-plan.md`) didn't match reality, and what's still
waiting on an answer from Travis. See `netropy-ui-reference.md` for the
control-by-control UI inventory this was built alongside.

Target: **NTG 5.0 at `192.168.173.89`** since 2026-09-30 (firmware 5.0.7 →
5.0.7b). Entries before that were found on the 4.0 VM at
`192.168.173.111:8080`, a dedicated lab VM (confirmed not shared — see "Plan
questions the product answered" below). Suite coverage: plan areas T1–T14.

The running write-up of the 5.0 work — status table, evidence, and what
changed in the suite — is `docs/ntg5-investigation-log.md` (shown at the top
of the dashboard's Findings tab).

---

## Observed 2026-10-11 on NTG 5.0.9 / WAN emulator 5.1.5 (not yet reproduced as tests)

Seen while mapping the UI and building `pages/`. None was clicked through
to confirm, because each would act on someone else's testbed or on shared hardware.

1. **Ownership is enforced inconsistently in the UI.** Logged in as `test`,
   on admin's active testbed "TE": the dashboard tile disables Start ("Owned
   by admin. Only its owner or an admin can change it."), but its Stats page
   shows `▶ Start`, `Start Traffic` and `Delete run` enabled. The Port Status
   `Release` button is also enabled on admin's Ports 3/4, while
   `GET /units/local/ports` reports `releasable: false` for them. Either the
   server refuses (and the UI shouldn't offer it) or it doesn't (a permission bug).
2. **Toasts cover the "← Dashboard" button** for about 5 s after any save or
   create. A click on it waits until the toast fades. The suite now closes
   toasts first.
3. **Unlabelled controls (accessibility):** the Load profile checkbox, the
   Add Stream modal's Name and Quantity fields, the Network step's CIDR select
   (column header just "/") and the gateway field (accessible name is its
   placeholder "none"). On the WAN emulator, no form control has an accessible
   name, only `name=` attributes, and the icon buttons have empty names.
4. **WAN emulator .213 Engine Log: "redundant power supply failure"**
   (Oct 06 00:32:49). This is a hardware warning for whoever owns the box.

## Observed 2026-10-19 (NTG 5.0.12, WAN emulator .213)

Found while building the T18–T21 WAN library (endpoints, presets, edits).

1. **NTG .212 is now build 5.0.12**, updated from 5.0.10 without notice
   (the second silent update in a week). NTG Port 4 now links at 10 Gbps;
   it was 1 Gbps through October.
2. **WAN emulator: Create Endpoint with no IP address silently does
   nothing.** With a label, port, protocol and action set but the IP
   Address box empty, the button sends a request, the form stays open, no
   endpoint is stored, and no error shows. With an address it saves. The
   form should say an address is required, or accept "any".
3. **WAN emulator: the path presets button and its menu have no accessible
   names or roles** (a folder icon; groups open on hover only, so keyboard
   users can't reach the items).
4. **NTG counts delivered frames as lost after a long delay, and says the
   tail settled (T19c, reproduced 2/2).** 2 s delay each way through the
   emulator, 100 Mbps, 1/8/1 s run: the emulator delivered every frame
   (73,818 of 73,818 each way, 0 dropped), but the NTG saved 70,016 and
   69,888 received (5.2 % and 5.3 % "loss", about 3,800 frames each way,
   roughly the last half second of traffic). The same saved run says
   `tail-not-settled: false` with a 3.3 s tail, longer than the delay. So
   either the NTG stops counting before its own tail window ends, or it
   drops late-arriving frames from the count without flagging the tail.
   The average latency it measured was right (2,000 ms). Bypass baseline
   of the same spec: 0 % loss. Overlaps the earlier lost-run finding.
5. **NTG jitter is inter-frame, so an order-keeping network hides it
   (T18a, a fact to confirm, not a bug).** Normal delay mean 20 ms,
   σ 5 ms, with the emulator keeping frames in order: latency spread
   5.4–34.9 ms, but the NTG's avg jitter is 0.051 ms. Independent delays
   would give about 5.6 ms (2σ/√π). Worth asking which jitter definition
   the NTG documents.
7. **5.0.12 removed the DHCP Pre-Acq diagnostics card and added a NAT card.**
   The editor's Connectivity diagnostics (still "WORK IN PROGRESS") now has
   ARP, Ping, Traceroute and NAT ("Rewrite the outer-IPv4 destination on
   egress"). `test_t13_dhcp_pre_acq_renders_not_supported` checked that card, so
   it was deleted (with the now-empty T13 area) on 2026-10-19. Also seen
   the same day: the unit had **no testbeds at all** (other users' included),
   most likely cleared by the upgrade.
6. **The NTG transmits in 32-frame bursts at line rate (fact, measured).**
   Below a WAN cap, average latency rises by the delay plus 16.5
   frame-times at the cap, exactly a 32-frame burst's mean queueing: 4G
   LTE 13.2 ms (15 Mbps) / 15.9 ms (12.5 Mbps), GEO 16.5 ms (12 Mbps) /
   65.7 ms (3 Mbps). Matches the TX burst field's maximum (32; "blank =
   datapath default"). Users measuring a slow link will see this.

## Observed 2026-10-16 on NTG 5.0.10 (not yet reproduced as tests)

Seen while building T16b, read-only (the criteria popover was opened on an
existing run and cancelled). The unit was updated from 5.0.9 to 5.0.10
without notice; the hardware-free suite still passes on it (72/73, the one
failure intermittent, see below).

1. **The "Edit pass criteria" control is an unlabelled ⚙ button.** Its only
   description is a custom `data-tip` tooltip, so its accessible name is "⚙".
   The popover it opens has no dialog role, and its three number inputs (Max
   loss %, Max latency ms, Min Rx % of line) sit next to `<label>`s that
   aren't tied to them, so none has an accessible name. The suite finds them
   by their rule's text block; a `data-testid` or `aria-label` would do.
2. **Units differ between the UI and the API for Max latency**: the popover
   takes milliseconds, the Controller stores `max-latency-us` (µs). Fine if
   converted consistently; worth one test (T16b checks Max loss only).
3. **The API documentation contradicts the UI on runs with no criteria**:
   `/tests/{key}/runs/{id}/criteria` says "a run with no rule set has no
   verdict", but every such run shows PASS or FAIL (the "loss-based default"
   below). Admin's TE-01 has two FAIL runs with `criteria: {}` at 100 % loss.
4. **The shared `test` login makes `mine` meaningless for ownership.**
   Another user's SessionStrike testbed "SS" held Ports 3/4 under `test`, so
   the Controller reported them `mine: true` to the suite. The suite used to
   treat `mine` ports as its own (and Speaker 1's `release_ports` would have
   released them, deactivating "SS"); both now go by testbed name instead.
   Not a product bug, but a reason for per-person accounts on shared boxes.
5. **The editor shows "saved" before the server has the change.** The
   UNSAVED badge clears the moment Save *sends* `PUT /tests/<name>`, not when
   the Controller answers (probe, 4/4: badge gone at +0.03 s, config readable
   via the API ~0.05–0.1 s later). Two t0 self-tests read the config straight
   after Save and intermittently got the old one (2 of 4 full runs). Not data
   loss, but if a save were refused the user would already have been told it
   saved; whether the badge comes back on an error is untested. Two more
   details from the probes: on 5.0.10 the badge's text is "UNSAVED" only
   through CSS (the suite's exact-text wait had silently stopped waiting),
   and GET /tests/<name> can still return the old config ~0.1 s *after* the
   PUT answered 200 (1 of 4), a read-after-write gap for API users. The
   suite now waits for the PUT's 200 and Save going disabled
   (`TestbedEditorPage.save`), and its API read-backs poll briefly.

6. **NTG verdicts and loss through the WAN emulator (T16/T17, first runs).**
   The NTG's loss and latency numbers are right to the frame: its lost
   frames equal the emulator's drops exactly at 1 %, 2 %, 5 % loss and under
   a 100 Mbps cap. Pass criteria work as the popover says (Max loss 1 % →
   FAIL, 5 % → PASS on a 2 % run). With no criteria set, the "loss-based
   default" FAILed a 2 % run but PASSed a 0.0002 % one, so the default
   threshold is somewhere between; still undocumented.
7. **Port links still flap on 5.0.10.** Straight after T16b, Port 4 reported
   0 Mbps and then Port 3 oper-status "unknown"; both were back up within a
   few minutes. Same symptom as "Port 4 link speed changes on its own"
   below. The WAN tests now wait up to 30 s for links before a run.

## Confirmed product issues

Reproduced directly, not inferred from a single failed run.

### NTG 5.0: a frame smaller than the stream's header size silently loses the run
Found 2026-10-01 on 5.0.7b (`192.168.173.89`), T14. If a stream's frame
size is smaller than the headers that stream actually sends (plus the
4-byte FCS), Start is accepted (activate and start both succeed, Stop is
shown), the run looks live for a while, and then Statistics falls back to
"LIVE · IDLE — Ready to start traffic. Ports are armed and idle." **No run is
saved and no error or toast appears.** The unit itself stays healthy — the
next run works. The editor accepts any frame size, so nothing warns the user.

Measured on Port 3 ⇄ 4 at 500 Mbps (lost = no saved run; every pass had
0.000 % loss): UDP, ICMP, ARP pass at 64 B (they need ~46 B). UDP/IPv6
(needs 66 B) is lost at 64 B, passes at 128 B. DNS (~70 B) lost at 64 B,
passes at 256 B. NTP (94 B) lost at 90 B (6/6), passes at 128 B. **TCP's
cut-off is exactly 70 B** — 64, 66 and 68 B are lost; 70, 72, 80, 96 and
128 B pass — matching a 32-byte TCP header (20 B + 12 B of options). TCP/IPv6
(90 B) lost at 64 B, passes at 128 B. HTTP lost at 64 B, passes at 256 B
and 1500 B. No counter-example across 9 protocols.

This also explains the TCP/HTTP 64-byte "bad state" reported by email on
2026-09-30: on 5.0.7b those runs are lost the same way, but the unit doesn't
stay broken (health stays online; a UDP canary right after passes). On 4.0,
NTP at 90 B ran fine, so this may be a 5.0 regression; the 4.0 "VXLAN: Start
never begins traffic" entry below had the same "armed and idle" symptom.
The suite reports these as **system failure**.
Status: confirmed and isolated — ready to report to the engineer (ask: validate
frame size against the stream's headers, or handle short frames, and never
end a run with no record and no error).
— `tests/t14_64b_frame_bad_state/test_t14_frame_size_vs_headers.py`,
`tests/t14_64b_frame_bad_state/test_t14_64b_frame_protocols.py`

### NTG 5.0: Port 4 link speed changes on its own
Seen 2026-09-30/10-01 on `192.168.173.89`. Port 4 reported 10G, then 1G,
then 0 M (link still "up"), then 1G again, while the other seven ports
stayed at 10G. At 1G the Port 3 ⇄ 4 path tops out around 1.4 Gbps total (a
3 Gbps two-stream test lost 52.5 %). In the first 5.0 probe run Port 4 also
transmitted only ~80–100 Mbps against a configured 1000 Mbps while Port 3
sent the full rate — the run still showed PASS, and the headline "Avg TX"
hid it (only the Per-Port table shows it). Ports 3/4 are cabled through the
WAN emulator, so the cable, SFP or emulator port are likely suspects.
Status: unresolved, needs someone at the rack; the ~1/10-rate observation is
a single observation.
— T10 lifecycle tests on Port 3 ⇄ 4

**Update 2026-10-05, reproduced on `192.168.173.212` (4/4 runs) and measured
by two boxes:** with both ports stored as `rate-mbps: 500`, Port 4 sends
46.5 Mbps on average (90,222 frames) against Port 3's 465.5 Mbps (902,220).
The WAN emulator in the path counts exactly the same frames per direction,
so the shortfall is real transmission, not a stats error. The run PASSes with
0 % loss, because loss only compares sent with received. The NTG port list
shows Port 4 at `speed-mbps: 0` (link "up"), the testbed stores it as 10000,
and the emulator port it's cabled to links at 1000 Mbps. Likely cause: the
rate is applied as a fraction of the nominal 10G (5 %) on a link that's
really 1G, giving 50 Mbps. Two product issues, whatever the link cause:
(1) a port can silently send a tenth of its configured rate, and (2) the
verdict and loss % don't reveal it. Suggest a pass/fail rule on TX rate vs
configured rate (the NTG's "min Rx % of line rate" criterion may cover it).
— T15 (`tests/t15_wan_emulator`), run history `metrics` checks

### "Copy UID" silently does nothing
The copy-to-clipboard control next to every testbed/profile UID produces no
clipboard write, no toast, and no console error. Root cause: the box is
served over plain HTTP at a private IP, and Chrome only exposes
`navigator.clipboard` on secure contexts — it does not treat private-LAN IPs
as secure. `window.isSecureContext` is `false` here, so the click handler has
nothing to call and the failure is swallowed silently. Real users hitting
this box in Chrome see the same nothing-happens behavior.
Fix options: serve over HTTPS, add a `document.execCommand('copy')`
fallback, or at minimum surface a visible error.

### No client-side validation on Network Configuration's IP or MAC fields
A malformed IP (`not.an.ip`), an out-of-range octet (`10.0.0.999`), and an
invalid MAC (`zz:zz:zz:zz:zz:zz`) are all accepted verbatim, with no error
and no clearing on blur.
— `tests/t6_network_config/test_t6_invalid_ip_mac_no_validation.py`

Extends to cross-field consistency too, not just per-field malformed
values: a testbed with mismatched source/destination subnet masks (`/25`
on one side, `/28` on the other, same conversation) was accepted with no
warning at all and ran successfully — traffic flowed correctly (non-zero
Tx/Rx on both sides, PASS reported), so this is a pure validation gap, not
something that breaks the traffic path.
— `tests/t10_t12_lifecycle/test_t10_asymmetric_subnet_pairing.py`

### Declared numeric bounds aren't enforced — on most fields
Wizard step 1's Line Rate has no declared maximum at all, so a value far
above a port's real 10 Gbps ceiling is accepted with no clamp. Stream Frame
Size *does* declare real `min="64" max="9216"` HTML attributes — and still
doesn't enforce either bound; 32 and 50,000 both go through untouched. The
one exception found across the whole suite: Traffic and Load Profile's TX
burst field genuinely clamps to its declared max of 32.
— `tests/t5_ports/test_t5_line_rate_validation.py`,
`tests/t7_streams/test_t7_frame_size_bounds.py`,
`tests/t8_traffic_load/test_t8_tx_burst_bandwidth_cap.py`

### Testbed activation 502s permanently — root cause found: a 15-character name limit
What looked for weeks like genuine intermittency turned out to be fully
deterministic. `POST /ctrl/v1/tests/{name}/activate?wait=15` returns `502
Bad Gateway` (`"Remote end closed connection without response"`) for any
testbed whose name is **16 characters or longer** — every time, permanently,
for that object — while a name of 15 characters or fewer activates cleanly,
every time. Confirmed with a clean boundary test (two names differing by one
character and a shared prefix: 15 chars → `200`, 16 chars → `502`) and
reproduced across ports, protocols, and line rates.

This explains everything that made it look intermittent or automation-
specific over many earlier investigation sessions: every automated test in
this suite followed a descriptive naming convention well over 15 characters
(`T10-T12-Lifecycle-ICMP-5Gbps-64B`, `...-DeleteMe`, etc.), while every
human-made testbed on the box (`xx`, `TE-01`, `TA`, `Sony_Demo`) happened to
be short. Extensive earlier elimination work (config content, session
freshness, save/activate timing, `navigator.webdriver` automation
fingerprinting, interaction pace) correctly ruled out everything it tested —
name length just was never isolated as the variable until a dedicated
boundary test did.

Two things worth fixing on the product side:
1. **No validation at creation time.** The backend silently accepts and
   saves a name it can never activate — `POST /ctrl/v1/tests` and the
   following `PUT` both return success. It should reject or truncate an
   over-length name at save time, and the wizard's name field has no
   `maxlength` attribute to stop one from being typed in the first place.
2. **The frontend shows nothing when activation fails.** Whether the cause
   is this or the VXLAN issue below, a failed activate leaves the wizard
   silently stuck on "Apply" forever — no toast, no error text, no retry.
   The only way to see it's failed at all is to watch network traffic
   directly. This UX gap is the reason the real cause took this long to
   isolate. A third trigger for the same silent-failure pattern, confirmed
   2026-09-15: attempting to activate a testbed that reuses a port already
   claimed by another *active* testbed. The wizard's own Ports step
   correctly labels the port `⚠ in use by testbed X`, but doesn't disable
   the toggle or block Apply — Apply just quietly fails to activate, with
   no visible error, and the still-running testbed is left unharmed. See
   `tests/t10_t12_lifecycle/test_t10_port_conflict_while_active.py`.

Status: **root cause confirmed and fixed test-side** (every test that
activates a testbed now asserts its name is ≤15 characters before trying —
see `conftest.assert_activatable_name`). Both product-side issues above are
still open, pending Travis.

### VXLAN: activation succeeds but Start intermittently never begins traffic
A separate, still-open issue found while adding VXLAN protocol coverage.
Activation itself works (the testbed goes active, `Deactivate` appears), but
clicking Start doesn't always actually begin the run — the Statistics view
shows "Ready to start traffic / Ports are armed and idle" instead of a live
or finished result. A network-logged repro isolated it: `POST
/ctrl/v1/tests/{name}/start?wait=15` returned `200` with a **self-
contradictory body** — `"traffic-running": true` alongside `"datapath-
state": "IDLE"` in the same response — and the page then became completely
unresponsive. Seen on 2 of 3 attempts with an identical config; the 3rd ran
clean end-to-end. Only observed with VXLAN so far (DNS, NTP, ARP, and the
existing UDP/TCP/ICMP siblings have been reliable). Kept in the suite as
`xfail(strict=False)` — it documents the bug without blocking the suite
either way, and would surface as an unexpected pass (not silently) if it
stops reproducing.
Status: intermittent, unresolved. Update (2026-09-15): reproduced again in
a testbed mixing three streams together — ARP, DNS, and VXLAN — not a
VXLAN-only testbed. Same self-contradictory `"traffic-running": true` /
`"datapath-state": "IDLE"` pattern. Confirms the bug isn't specific to a
VXLAN-alone config; everything else about the cross-layer mix (adding all
three stream types, Apply/Activate) worked cleanly.
— `tests/t10_t12_lifecycle/test_t10_cross_layer_multistream_arp_dns_vxlan.py`

### Restarting Start after Stop can silently end a run in a few seconds
Stopping a live run, then clicking Start again on the same still-Applied
testbed (without Deactivating first), can produce a "run" that silently
self-terminates after roughly 2–4 seconds instead of running its configured
duration — no error, no toast, nothing visibly wrong. The dashboard tile
behaves as if a normal run completed. Found while cycling one testbed
through Start → Stop → Start twice in a row: the first Start/Stop cycle
behaved exactly like every other lifecycle test in this suite; the restart
immediately after is where it broke.

Distinguishable from the 15-char-name 502 bug above: no 502, activation
itself already succeeded once, the name was well under the limit, and
nothing here involves re-activating — only Start/Stop after a single Apply.

Status: **reproduced twice** (once in the actual test run, once in a
follow-up instrumented diagnostic polling tile state every 0.5–2s), but a
third confirmation attempt was blocked by this environment's own repeated-
hardware-action safeguard before it could run. Treat as a strong lead, not
yet a fully confirmed issue — worth a deliberate repro from Travis or Logan
before this graduates further.
— `tests/t10_t12_lifecycle/test_t10_rapid_stop_restart_cycle.py`

### Start double-click can leave a completed run's Stats view stuck on "never started"
Rapidly double-clicking Start (a single `click_count=2` gesture, not two
separate slow clicks) was handled correctly at the network level — exactly
one `POST .../start` call fired, no duplicate submission — and the run
completed its full configured duration normally (Stop stayed visible for
the whole ramp). But afterward, clicking the dashboard tile's "Stats"
button — the same action every sibling lifecycle test in this suite uses
successfully right after a completed run — showed the "Ready to start
traffic / Ports are armed and idle" empty placeholder instead of the
completed run's result. The run-history table never appeared.

Working hypothesis, not confirmed: the second click event landed on the
Statistics view's own "Start traffic" button microseconds after the SPA
navigated into it, planting a stale "about to start" expectation in
frontend state that outlived the real, successfully-completed run.

Status: single observation only (this environment's stateful-action policy
allows one genuine run per exploratory test) — flagging as a real anomaly
worth a deliberate repro, not yet confirmed root cause.
— `tests/t10_t12_lifecycle/test_t10_double_click_start_race.py`

### Any backend write while a run is live can silently interrupt it — not scoped to that testbed
**Scope widened 2026-09-15** — originally written up as "any mutating
action *against* a live testbed" (a write that references that specific
testbed's ID). A third test built specifically to probe the boundary
found that framing is too narrow: a write with **zero relationship** to
the live testbed — different object, different name, no shared ports, no
ID reference anywhere — still disrupted it, and more severely than either
original trigger. See "the boundary itself" below for the new evidence
before the original two triggers that motivated it:

Two independent tests originally found the same symptom through two
completely different triggers:

- **Editing a live testbed's config.** With a testbed genuinely live
  (confirmed non-zero Tx/Rx), navigating into Edit, changing the Streams
  step's frame size, and clicking Save is not blocked — no disabled
  fields, no "can't edit while running" warning, Save reports success
  silently. But the in-progress run doesn't survive it: Stop disappears
  within seconds (far short of the configured hold), Port 3's packet
  counters reset from real traffic back to 1/1 (a restart-from-scratch
  signature, not a continuation), and the eventual run-history row has a
  real Started-At/Duration but an **empty Result cell** — the outcome
  isn't delayed, it's lost. Reproduced twice, including a deliberate
  20-second poll specifically to rule out a read-before-populated race
  (matching the pattern the UDP reference test already uses for its own
  PASS check) — the empty Result held up both times.
  — `tests/t10_t12_lifecycle/test_t10_edit_config_while_active.py`
- **Cloning a live testbed.** Clone never touches the original's own
  config — it only reads it to produce a new draft — and the clone
  itself came up correctly as a fresh, inactive, port-free draft (no
  shared ports with the still-running original, confirmed by reading the
  clone's line-rate field `disabled` state directly). Despite the
  original never being touched again after confirming it was live, its
  Stop button vanished within seconds of the clone action completing —
  the identical "run interrupted almost immediately" symptom, through a
  trigger that doesn't mutate the live testbed at all, only references
  its ID.
  — `tests/t10_t12_lifecycle/test_t10_clone_while_active.py`
- **The boundary test — an action with NO relationship to the live
  testbed at all.** Built `T10-LiveCtrl` (UDP, Port 3+4), confirmed it
  genuinely live (real, climbing Tx/Rx counters on Port 3), then created
  and immediately deleted a second, wholly separate draft testbed
  (`T10-Unrelated`) — two real backend writes that never referenced
  `T10-LiveCtrl`'s name or ID, and (confirmed directly by reading its own
  Ports step before deleting it) never touched Port 3 or Port 4 either.
  32.9 seconds into `T10-LiveCtrl`'s 90-second configured hold — nowhere
  near natural completion — its dashboard tile showed **neither `Stop`
  nor `Stats`**. That second part matters: the Edit/Clone triggers above
  both left the live testbed ACTIVE-but-idle (tile still showed
  `Stats`/`Start`) after Stop vanished; here `Stats` was gone too, reading
  as a full drop out of ACTIVE state rather than merely "stopped early."
  One recorded run, not yet reproduced a second time (deliberately, per
  the task that requested it — one genuine attempt on shared hardware,
  not iterated); the deeper checks the two triggers above also captured
  (packet-counter reset, empty run-history Result) weren't reached
  because the leading assertion raised first — the same disclosed gap the
  Clone test itself accepted when its own leading symptom raised early.
  — `tests/t10_t12_lifecycle/test_t10_unrelated_action_during_live_run.py`

Since Clone doesn't touch the source's configuration, "editing broke it"
isn't the real mechanism for the first two triggers — and the boundary
test shows the mechanism isn't even "references a live testbed's ID" at
all. The honest reading now is closer to "any backend write while a run
is in progress can disrupt whatever happens to be live," not "actions
taken against that specific testbed." Likely the same root cause as
"Restarting Start after Stop" above either way, but this is no longer
safely describable as a scoped, avoidable-by-not-editing-the-live-
testbed issue — treat it as a systemic backend concern with a
correspondingly larger blast radius, not three variants of one narrow
bug.
Status: reproduced across 3 tests / 5 total runs (2 for the edit case, 1
clean run for the clone case, 2 for the boundary case), no confirmed root
cause. The boundary case's second confirming run (2026-09-15) reproduced
at nearly identical timing to the first (31.6s vs. 32.9s into the
configured hold) with an unmodified test — no longer treating "any write,
anywhere" as a one-off; this reads as a deterministic, high-priority
systemic issue rather than an intermittent one. Deeper diagnostics
(packet-counter reset signature, whether a run-history entry appears at
all) remain uncaptured — the test's own leading assertion raises before
either check runs, so closing that gap needs a purpose-built test that
polls in the background (e.g. via network log) rather than only reading
disappearing UI elements.

### Deactivate mid-run behaves differently from Stop mid-run
Clicking Deactivate directly while a run is live (skipping Stop entirely)
does cleanly end the run without a crash or stuck state, but has two
effects Stop mid-run doesn't:
1. **It implicitly releases the ports.** Both ports came back `Available`
   (not `Reserved`) with no separate Release click — every other lifecycle
   test in this suite confirms Stop alone leaves ports `Reserved`,
   requiring an explicit Release. A user deactivating to reconfigure loses
   their reservation without being told, and on a shared box someone else
   could claim the port immediately after.
2. **Possible lost run-history entry — a strong lead, not yet confirmed.**
   The testbed card captured during this test was missing the "Reports:"-
   style run-count control entirely (present on other testbeds on the
   box), suggesting the run ending via Deactivate-without-Stop may not get
   recorded in run-history at all. This was incidental evidence (captured
   for an unrelated assertion), not a direct read of the runs table — the
   test's own run-history check exists but was never reached.
Status: port-release behavior confirmed; lost-history-entry is an
unconfirmed lead worth a direct follow-up check.
— `tests/t10_t12_lifecycle/test_t10_deactivate_mid_run.py`

### Port links drop to "No Link" after activation — recurring, 4 incidents
Ports have gone `Down / 0M / No Link` after activation on four separate
occasions: Port 5+6 once, Port 7+8 once (both the *first-ever* activation
attempted on that specific pair), all of Port 5–8 simultaneously during a
full-suite run, and most recently Port 5+6 again after a passing ARP
lifecycle test. Each time, the drop happened independent of test-script
cleanup — teardown completed normally regardless, and the triggering test
itself passed cleanly every time. The most recent incident is the strongest
data point yet against a config-based explanation: ARP at 10 Mbps is about
as far as this suite gets from the original (already-retracted) "high line
rate causes it" theory, and the link still dropped. Three of the four
incidents have self-recovered on their own within the same session; the
pattern itself hasn't. Port 5+6 specifically accounts for 3 of the 4
incidents — worth treating as a real, recurring hardware/driver issue tied
to that pair rather than a one-off, at this point.

### Couldn't produce a FAIL result through the UI on this hardware
Three deliberate attempts to force a failing run on Port 3+4 (wrong
destination IP, wrong destination MAC, and a genuine 10 Gbps/64-byte
overload for max packet rate) all still reported PASS at 0.000% loss. Rx/loss
counting on this box doesn't appear to be gated by L2/L3 address correctness
at all, and the appliance sustained true max line-rate/min-frame-size traffic
without measurable loss. If a FAIL case is needed for testing, it likely
needs a different mechanism (VLAN/tagging mismatch, traffic-mix edge cases)
— or may not be reachable through the wizard on this hardware at all.
— `tests/t10_t12_lifecycle/test_t10_fail_path_overload_max_rate_min_frame.py`
(xfail, by design)

### The pass/fail criterion is an undisclosed default
Every run checked so far shows the Result cell's tooltip reading
*"loss-based default (no pass criteria set)"*, next to an "Edit pass
criteria" control. What the default actually computes hasn't been pinned
down. **Update 2026-10-16:** the control is the result cell's ⚙ button. It
edits that one saved run's criteria after the fact (Max loss %, Max latency
ms, Min Rx % of line; empty = rule off, 0 = a real threshold), and the NTG
re-judges the run (`set-run-criteria` in the API). T16b
(`tests/t16_wan_loss/test_t16_loss_criteria.py`) uses it to test the
verdict against a known 2 % loss.

---

## Where the written test plan didn't match the product

### There is no "rename testbed" feature
The plan assumed an in-place rename control on the testbed editor. It
doesn't exist — the title is plain, non-editable text. The only way to give
a testbed a different name is Clone, whose confirm dialog pre-fills an
editable `<name>-copy` field.

### License gating has nothing to gate right now
The plan assumed RFC 2544 and SessionStrike would show as unlicensed. As
configured today, Traffic Engine, RFC 2544, and SessionStrike all read
**LICENSED** (valid through 26 Aug 2027). The gating test is blocked, not
failing — there's no unlicensed state on this box to exercise.

### The network-config 🔗 icons are one-shot sync buttons, not a live link
The plan described a toggleable link between a port's destination fields and
its peer's source fields. In practice, DST IP/Dest MAC auto-populate once
when a second port is enabled, then never again automatically — the 🔗
button has to be clicked each time to pull the current value across. There's
no on/off state.

### "Distribute across ports" is a bulk action, not a persistent mode
Same shape as the 🔗 icons: All Ports / Alternate / Sequence rewrite every
stream's Interface Port ID once, immediately, with no selected/active state
retained afterward.

### Auto-deactivate-on-completion isn't a reliable rule
Earlier observation had a testbed's card revert to inactive automatically
once its run finished. Later testing directly contradicted that: a testbed
that completed its ramp naturally stayed **ACTIVE** (`LIVE · IDLE`), and only
went inactive once ports were explicitly released. Whatever triggered the
first observation hasn't been isolated — treat completion state as something
to check live, not assume.

### The stats view and the Reports badge only exist in specific activation states
The rich metric-tabs/chart/scope-filter section of the Statistics page only
renders while a testbed is **ACTIVE** (live or idle); once fully deactivated
it's replaced by a "Testbed not active" placeholder and only the run-history
table remains. Conversely, the dashboard's "Reports: N" badge only appears
once a testbed is deactivated — while active, the card shows a "Stats"
button instead. Both routes reach the same page; which one's visible depends
on activation state.

---

## Plan questions the product answered

The plan flagged these as "document the behavior" items rather than assuming
an answer. Now confirmed.

- **Over-100% stream mix: rebalances and warns, never blocks.** Adding or
  removing streams auto-splits their share evenly; editing one stream's
  share auto-rebalances the rest to hold the total at 100%. Pinning a share
  that alone exceeds 100% is still accepted — other streams get pushed
  toward 0%, and a visible warning appears ("Pinned shares exceed 100% on
  Port N — trim them so the total fits") — but nothing is ever blocked.
- **Toggling a port off and back on keeps its configuration.** Line rate,
  direction, and other per-port wizard settings are retained across a USE
  toggle-off/on, not reset to defaults.
- **Network Profiles are shared across every user on the box.** Unlike
  testbeds (also global, but always addressed by a unique name), the Network
  Profiles list has no per-user scoping at all — a profile saved by one
  session shows up in the same dashboard card everyone sees. This makes
  "assert the list is empty" or "export with zero profiles" impossible to
  test safely without depending on, or deleting, someone else's saved work —
  both were left unautomated rather than faked.
- **The "Add Stream" protocol picker offers far more than UDP/TCP/ICMP** —
  IPv6 variants of all three, DNS and NTP (Application), SIP/RTP/RTCP (VoIP,
  all three tagged **WIP** in the UI), ARP and Raw Ethernet (Layer 2), and
  VXLAN (Tunnel). Every protocol creates exactly one stream per "Add
  Stream" — nothing needs a multi-stream setup. Two things not obvious from
  the picker's own description, confirmed only by actually creating each
  stream and reading its resulting layer chips: **DNS and NTP aren't their
  own layer** — they're plain UDP with a preset destination port (53/123),
  so their stream row shows a "UDP" chip, not "DNS"/"NTP". And **ARP has no
  IP layer at all** (`Ethernet → Payload` only, no default ports), yet the
  wizard's Network Configuration step still renders the full per-port
  IP/MAC form regardless of protocol — it's generic to the testbed, not
  stream-aware, so those fields are simply meaningless (and safe to leave
  at their auto-filled defaults) for an ARP-only stream. See
  `tests/t10_t12_lifecycle/test_t10_t12_lifecycle_{dns,ntp,arp,vxlan}_*.py`.
- **This box is a dedicated test VM, not a shared appliance with random
  other users** (confirmed by Logan). This reframes — but doesn't
  retroactively confirm a specific cause for — a few findings above that
  speculated about "another user": the recurring Port 5–8 link-down
  incidents and the stray T9 testbed/profile found during the full-suite
  run are more likely leftovers from this suite's own earlier or concurrent
  runs than a genuinely unrelated third party. The suite's caution around
  shared-state (unique `-DeleteMe` names, never asserting on global counts)
  stays in place either way — it's cheap insurance regardless of who else
  might be on the box.

---

## Still open, pending Travis

Nothing below is guessed at in the test suite — each blocks a specific plan
item until it's answered.

1. **What's the actual PASS/FAIL loss threshold?** A run showed nonzero
   dropped frames on individual ports yet still passed at 0.000% aggregate
   loss. No strict loss-threshold assertions have been written until this is
   confirmed.
2. **Can the frontend add `data-testid` attributes?** Current selectors are
   role-based and scoped to row/card, which works, but several controls
   (icon-only buttons, testbed tiles) have no accessible name at all and are
   matched by tooltip text or CSS class as a fallback.
3. **What does per-port Reset actually do to the link?** Reset All is
   already off-limits by policy. Per-port Reset was never confirmed either,
   so no automated test clicks it — same caution, unresolved.
4. **What's the session timeout length?** The rest of authentication
   (login, logout, invalid password, concurrent sessions) is covered;
   timeout is the one deliberately-skipped item rather than a guessed value.
5. **Is a second test account available?** Only one account is configured. A
   second browser session on the same account sees an already-reserved port
   as its own, not a conflict — so "reserve a port another user holds →
   blocked with a clear error" can't be reproduced without a genuinely
   separate identity.

Answered since the last pass: **the box is a dedicated test VM**, not a
shared appliance — see the note under "Network Profiles are shared across
every user on the box" above.

---

## Test suite coverage

`hardware_free` areas run anytime; `stateful` areas reserve real ports and
generate real traffic.

| Area | Covers | Class |
|---|---|---|
| T1 · Authentication | Login, logout, invalid password, concurrent sessions | free |
| T2 · Dashboard | Load, port table, license gating display | free |
| T3 · Port management | Reserve/release, same-account reservation, Reserved By/Test Name while active | mixed |
| T4 · Testbed lifecycle | Create, validate, duplicate, delete, export/import round-trip | free |
| T5 · Wizard: Ports | USE toggle, peer port, line rate validation, roster/topology | free |
| T6 · Wizard: Network Config | Host-count math, IP Inc, MAC auto-fill, Gateway/Dest MAC, Encap | free |
| T7 · Wizard: Streams | Add/delete/clone, frame size, port distribution, layer editor | free |
| T8 · Wizard: Traffic/Load | Stream-mix rebalancing, ramp math, TX burst/bandwidth cap | free |
| T9 · Network Profiles | Save from wizard, select-to-populate, export/import | free |
| T10 · Activation lifecycle | Live badges, dashboard active count, two simultaneous testbeds, default addressing, stop-mid-run, overload fail-path, 7 protocols (UDP/TCP/ICMP/multi-stream/DNS/NTP/ARP + VXLAN xfail), port-conflict-while-active, cross-layer 3-protocol multistream, asymmetric subnet pairing, rapid stop/restart cycling, Start double-click race, deactivate-mid-run, edit-config-while-active, clone-while-active, unrelated-action-during-live-run (boundary test) | stateful |
| T11 · Live statistics | Metric tabs, scope/signal filters, unit toggle, zoom | stateful |
| T12 · Reports & exports | Run history, all 5 export formats, delete run, Reports badge | stateful |
| T13 · Connectivity diagnostics | DHCP Pre-Acq not-supported state (rest deferred, product WIP) | free |

---

## Testing environment

**NTG 5.0 unit (`192.168.173.89`), from 2026-09-30:** only Port 3 ⇄ Port 4
are cabled as a pair — runs on 1 ⇄ 2 and 5 ⇄ 6 transmit but receive nothing
(e.g. 304 Mbps sent, 0.0 received → FAIL), so tests there fail for cabling,
not product, reasons. Port 4's link speed is unstable (see "Port 4 link
speed changes on its own"). The unit was rebooted and upgraded from 5.0.7 to
5.0.7b mid-session (~20:00 PDT 2026-09-30). All 71 hardware-free tests pass
3/3 on 5.0; the traffic tests are being rebuilt for 5.0's Start flow — see
`docs/ntg5-investigation-log.md`.

**4.0 VM (`192.168.173.111:8080`), before 2026-09-30:**

The full 85-test suite was run once, end-to-end, headless and serial: **81
passed, 1 passed-as-expected-fail, 3 failed**, in 18m11s. Both root causes
were environmental, not product regressions:

- **Port 5–8 down again** — the third occurrence of the recurring link-down
  pattern above, broke the one lifecycle test targeting Port 5/6.
- **A stray testbed and network profile** left behind by a transient timing
  flake (a toast overlay intercepting a click, under more background load
  than any single test sees in isolation) cascaded into a second, unrelated
  test whose assertion depended on the dropdown being clean. Both objects
  were confirmed stray and removed; the flake's root cause wasn't isolated
  further.

Every test in the suite has independently passed 3 consecutive clean runs in
isolation before being committed. This was the first time all 85 ran
together in one pass — worth knowing that "green file-by-file" and "green
end-to-end" aren't automatically the same guarantee on this box.

## Dashboard failures — pending review

Logged automatically when a test fails through the dashboard — each entry is one run's raw evidence, not yet reviewed. Ask Claude to review the pending entries in a session: it reads the trace/screenshot and either promotes a real one to "Confirmed product issues" above, or notes why it isn't (test/selector issue, inconclusive, etc.), then marks the entry reviewed.

### 2026-09-15 00:04 UTC — tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py::test_t10_default_addressing_activation

**Status:** pending review

Failure message: failed on setup with "playwright._impl._errors.TimeoutError: Page.goto: Timeout 30000ms exceeded.
Call log:
  - navigating to "http://192.168.173.111:8080/", waiting until "load""

Trace summary:
```
(no trace captured)
```

### 2026-09-15 02:36 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_tcp_2gbps_512b.py::test_t10_t12_lifecycle_tcp_2gbps_512b

**Status:** pending review

Failure message: failed on setup with "playwright._impl._errors.Error: Page.goto: net::ERR_ABORTED; maybe frame was detached?
Call log:
  - navigating to "http://192.168.173.111:8080/", waiting until "load""

Trace summary:
```
(no trace captured)
```

### 2026-09-15 19:19 UTC — tests/t13_connectivity_diagnostics/test_t13_dhcp_pre_acq_not_supported.py::test_t13_dhcp_pre_acq_renders_not_supported

**Status:** pending review

Failure message: failed on setup with "AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: Netropy Traffic Generator | Sign in Username
- textbox "username": test
- text: Password
- textbox "password": test
- text: Controller unreachable — is the backend running?
- button "Sign in"
- text: Controller online — unit local reachable Powered by
- link "Apposite Technologies":
  - /url: https://www.apposite-tech.com
- text: © 2026
Error: element(s) not found 
Call log:
 

Trace summary:
```
(no trace captured)
```

### 2026-09-15 22:44 UTC — tests/t10_t12_lifecycle/test_t10_asymmetric_subnet_pairing.py::test_t10_asymmetric_subnet_pairing

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: Netropy Traffic Generator | Sign in Username
- textbox "username"
- text: Password
- textbox "password"
- button "Sign in"
- text: Controller online — unit local reachable Powered by
- link "Apposite Technologies":
  - /url: https://www.apposite-tech.com
- text: © 2026
Error: element(s) not found 
Call log:
  - Expect "to_be_visible" with timeout 75000ms
  - waiting for get_by_role("button", name="

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: net::ERR_CONNECTION_REFUSED
Console error: Failed to load resource: the server responded with a status of 401 (Unauthorized)
Console error: Failed to load resource: the server responded with a status of 401 (Unauthorized)
Console error: Failed to load resource: the server responded with a status of 401 (Unauthorized)
Console error: Failed to load resource: the server responded with a status of 401 (Unauthorized)
Console error: Failed to load resource: the server responded with a status of 401 (Unauthorized)
Console error: Failed to load resource: the server responded with a status of 401 (Unauthorized)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-AsymCIDR"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-AsymCIDR', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-AsymCIDR"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.20.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.20.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '28'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.20.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.20.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '50', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Apply"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="Deactivate"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible',
...(truncated)
```
Screenshot: `webapp-artifacts/7fdaaf78-6f30-4c5d-8f2e-bfde9799604f/1/test-failed-1.png`
Trace: `webapp-artifacts/7fdaaf78-6f30-4c5d-8f2e-bfde9799604f/1/trace.zip`

### 2026-09-15 22:46 UTC — tests/t10_t12_lifecycle/test_t10_double_click_start_race.py::test_t10_double_click_start_race

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 15, 2026 15:46:29 UTC Unit clock NTP server: not configured (sandbox) Sep 15, 2026 15:46:29 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 10%
- text: 10.4

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblApply"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblApply"i'})
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})
```
Screenshot: `webapp-artifacts/94e0cd94-93bc-41f0-8164-519881c01827/1/test-failed-1.png`
Trace: `webapp-artifacts/94e0cd94-93bc-41f0-8164-519881c01827/1/trace.zip`

### 2026-09-15 22:47 UTC — tests/t10_t12_lifecycle/test_t10_double_click_start_race.py::test_t10_double_click_start_race

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("button", name="Apply", exact=True)

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblApply"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-DblClick', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.9.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.9.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.9.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.9.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '60', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Apply"s]', 'strict': True, 'timeout': 30000})  FAILED: Timeout 30000ms exceeded.
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'time
...(truncated)
```
Screenshot: `webapp-artifacts/94e0cd94-93bc-41f0-8164-519881c01827/2/test-failed-1.png`
Trace: `webapp-artifacts/94e0cd94-93bc-41f0-8164-519881c01827/2/trace.zip`

### 2026-09-15 22:48 UTC — tests/t10_t12_lifecycle/test_t10_double_click_start_race.py::test_t10_double_click_start_race

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("button", name="Apply", exact=True)

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblApply"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-DblClick', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.9.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.9.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.9.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.9.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '60', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Apply"s]', 'strict': True, 'timeout': 30000})  FAILED: Timeout 30000ms exceeded.
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'time
...(truncated)
```
Screenshot: `webapp-artifacts/94e0cd94-93bc-41f0-8164-519881c01827/3/test-failed-1.png`
Trace: `webapp-artifacts/94e0cd94-93bc-41f0-8164-519881c01827/3/trace.zip`

### 2026-09-16 22:01 UTC — tests/t10_t12_lifecycle/test_t10_edit_config_while_active.py::test_t10_edit_config_while_active

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 16, 2026 15:01:59 UTC Unit clock NTP server: not configured (sandbox) Sep 16, 2026 15:01:59 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 46%
- text: 46 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/3/release -> 403 Forbidden
```
Trace: `webapp-artifacts/57fb3cfe-efa6-447e-bed8-22cc7deb64ba/1/trace.zip`

### 2026-09-17 23:42 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_udp_1gbps_1500b.py::test_t10_t12_lifecycle_udp_1gbps_1500b

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator(".tb-tile").filter(has_text="T10-Life-UDP").get_by_role("button", name="Stats")

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-UDP"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-Life-UDP', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-Life-UDP"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.0.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.0.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.0.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.0.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '50', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', '
...(truncated)
```
Screenshot: `webapp-artifacts/a8e8afd9-4d00-401d-9582-2ab3aec52b1b/1/test-failed-1.png`
Trace: `webapp-artifacts/a8e8afd9-4d00-401d-9582-2ab3aec52b1b/1/trace.zip`

### 2026-09-17 23:44 UTC — tests/t10_t12_lifecycle/test_t10_edit_config_while_active.py::test_t10_edit_config_while_active

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("button", name="Apply", exact=True)

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-EditLive', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.13.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.13.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.13.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.13.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Apply"s]', 'strict': True, 'timeout': 30000})  FAILED: Timeout 30000ms exceeded.
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> 
...(truncated)
```
Screenshot: `webapp-artifacts/b4577bf7-9d31-49cf-8e95-1b521891bbba/1/test-failed-1.png`
Trace: `webapp-artifacts/b4577bf7-9d31-49cf-8e95-1b521891bbba/1/trace.zip`

### 2026-09-17 23:50 UTC — tests/t10_t12_lifecycle/test_t10_clone_while_active.py::test_t10_clone_while_active

**Status:** pending review

Failure message: AssertionError: REAL BUG: the CLONE of a live testbed came up already in an ACTIVE (applied) state — its tile shows Start/Stats instead of Activate — despite this test never clicking Activate on it. A clone should land as a fresh inactive draft. Distinct from the Edit-while-active bug (which corrupts the ORIGINAL's run) — this is the clone itself inheriting state it never earned.

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-CloneX', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.17.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.17.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.17.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.17.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': '.tb-tile >> internal:has="div[title=\\"T10-CloneX\\"]" >> internal:role=button[name="Stop"i]', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.click({'selector': '.tb-tile >> internal:has="div[title=\\"T10-CloneX\\"]" >> internal:role=button[name="Stats"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Per-Port Aggregate Statistics"i', 'expression': 'to.be.visible', 'timeout': 15000, 'isNo
...(truncated)
```
Screenshot: `webapp-artifacts/d3d377ec-ce33-417e-bac1-6d403fca05b0/1/test-failed-1.png`
Trace: `webapp-artifacts/d3d377ec-ce33-417e-bac1-6d403fca05b0/1/trace.zip`

### 2026-09-18 00:03 UTC — tests/t10_t12_lifecycle/test_t10_clone_while_active.py::test_t10_clone_while_active

**Status:** pending review

Failure message: AssertionError: REAL BUG: the CLONE of a live testbed came up already in an ACTIVE (applied) state — its tile shows Start/Stats instead of Activate — despite this test never clicking Activate on it. A clone should land as a fresh inactive draft. Distinct from the Edit-while-active bug (which corrupts the ORIGINAL's run) — this is the clone itself inheriting state it never earned.

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> nth=-1'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> nth=-1 >> internal:role=button[name="Stop"s]'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> nth=-1 >> [data-tip="Delete"] button'})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> nth=-1 >> [data-tip="Delete"] button', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Delete"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Delete"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> nth=-1', 'expression': 'to.have.count', 'expectedNumber': 0, 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-CloneX', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-CloneX"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.17.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.17.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.17.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.17.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 
...(truncated)
```
Screenshot: `webapp-artifacts/8511ff77-3277-4f26-adc4-3d22216b0f0c/1/test-failed-1.png`
Trace: `webapp-artifacts/8511ff77-3277-4f26-adc4-3d22216b0f0c/1/trace.zip`

### 2026-09-18 00:06 UTC — tests/t10_t12_lifecycle/test_t10_deactivate_mid_run.py::test_t10_deactivate_mid_run_skips_stop_cleanly

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:06:16 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:06:16 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 25 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DeactLive"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-DeactLive', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-DeactLive"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.11.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.11.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.11.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.11.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': '.tb-tile >> internal:has-text="T10-DeactLive"i >> internal:role=button[name="Stop"i]', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.innerText({'selector': 'internal:role=row[name="Port 3"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 15000})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-DeactLive"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout'
...(truncated)
```
Screenshot: `webapp-artifacts/fedd6194-acce-49ba-8940-741106dc9fe5/1/test-failed-1.png`
Trace: `webapp-artifacts/fedd6194-acce-49ba-8940-741106dc9fe5/1/trace.zip`

### 2026-09-18 00:06 UTC — tests/t10_t12_lifecycle/test_t10_default_addressing_activation.py::test_t10_default_addressing_activation

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:06:40 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:06:40 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 25 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DefaultAddr"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/67a12e8f-b014-4cbc-8ade-1f49eb8ee42d/1/test-failed-1.png`
Trace: `webapp-artifacts/67a12e8f-b014-4cbc-8ade-1f49eb8ee42d/1/trace.zip`

### 2026-09-18 00:07 UTC — tests/t10_t12_lifecycle/test_t10_double_click_start_race.py::test_t10_double_click_start_race

**Status:** pending review

Failure message: AssertionError: BUG: double-clicking Continue did not land cleanly in the Statistics view within 15s — the second click event appears to have broken navigation (stuck on the modal, blank, or otherwise off the expected post-Continue route).
assert False

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-DblApply"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-DblClick', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-DblClick"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.9.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.9.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.9.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.9.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '60', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="Start"s]', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'clickCount': 2, 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 2000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})  FAILED: Expect failed
  Frame.innerText({'selector': 'body', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 
...(truncated)
```
Screenshot: `webapp-artifacts/9e4b43c8-57a3-4494-bec6-f26cc9431fe2/1/test-failed-1.png`
Trace: `webapp-artifacts/9e4b43c8-57a3-4494-bec6-f26cc9431fe2/1/trace.zip`

### 2026-09-18 00:09 UTC — tests/t10_t12_lifecycle/test_t10_edit_config_while_active.py::test_t10_edit_config_while_active

**Status:** pending review

Failure message: AssertionError: The Result cell for this run is still empty after a generous 20s poll (ruling out the population-race the UDP reference test's own PASS check guards against) — the run's recorded outcome appears to have been genuinely lost following the mid-run edit attempt.
assert ''
 +  where '' = &lt;built-in method strip of str object at 0x100610670&gt;()
 +    where &lt;built-in method strip of str object at 0x100610670&gt; = ''.strip

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-EditLive', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.13.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.13.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.13.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.13.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i >> internal:role=button[name="Stop"i]', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-EditLive"i >> internal:role=button[name="Stats"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Per-Port Aggregate Statistics"i', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})

...(truncated)
```
Screenshot: `webapp-artifacts/78f21499-78e4-433a-b87d-47e9d6eceb61/1/test-failed-1.png`
Trace: `webapp-artifacts/78f21499-78e4-433a-b87d-47e9d6eceb61/1/trace.zip`

### 2026-09-18 00:12 UTC — tests/t10_t12_lifecycle/test_t10_live_view_badges_and_controls.py::test_t10_live_badges_and_t11_stats_controls

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:12:05 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:12:05 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- 'heading "T10-LiveView · UID: 5557ad49 5557ad492b0b457abcfeb85317755fa7" [level=1]':
  - te

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-LiveView"i'})
  Frame.innerText({'selector': '.card-hdr >> internal:has-text="Testbeds"i', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'internal:attr=[placeholder="e.g. web-perf-01"i]', 'value': 'T10-LiveView', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Create draft"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': '.tb-tile >> internal:has-text="T10-LiveView"i', 'expression': 'to.have.count', 'expectedNumber': 1, 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-LiveView"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Ports"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.click({'selector': 'tr >> nth=1 >> .toggle .track', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'tr >> nth=2 >> .toggle .track', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'tr >> nth=1 >> input[placeholder="line rate"]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'tr >> nth=1 >> input[placeholder="line rate"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'tr >> nth=2 >> input[placeholder="line rate"]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'tr >> nth=2 >> input[placeholder="line rate"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="3 Streams"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name="✚ Add Stream"s]', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name="ICMP"s]', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="ICMP"s]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': '.pill >> internal:has-text="used"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'div >> internal:has-text="Disabled \\u2014 traffic runs at full rate"i >> nth=-1 >> .toggle .track', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fg >> internal:has-text="Ramp up"i >> input[type="number"]', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': '.fg >> internal:has-text="Ramp up"i >> input[type="number"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fg >> internal:has-text="Hold time"i >> input[type="number"]', 'value': '15', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': '.fg >> internal:has-text="Hold time"i >> input[type="number"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fg >> internal:has-text="Ramp down"i >> input[type="number"]', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': '.fg >> internal:has-text="Ramp down"i >> input[type="number"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/caff9efc-28c8-4932-9938-0a0f75b3ecdf/1/test-failed-1.png`
Trace: `webapp-artifacts/caff9efc-28c8-4932-9938-0a0f75b3ecdf/1/trace.zip`

### 2026-09-18 00:15 UTC — tests/t10_t12_lifecycle/test_t10_rapid_stop_restart_cycle.py::test_t10_rapid_stop_restart_cycle

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator(".tb-tile").filter(has_text="T10-RapidCycle").get_by_role("button", name="Stop")

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-RapidCycle"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-RapidCycle', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-RapidCycle"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.7.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.7.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.7.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.7.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '120', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': '.tb-tile >> internal:has-text="T10-RapidCycle"i >> internal:role=button[name="Stop"i]', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-RapidCycle"i >> internal:role=button[name="Stats"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Per-Port Aggregate Statistics"i', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': F
...(truncated)
```
Screenshot: `webapp-artifacts/675853ad-c889-4e40-8c72-f6bd0ecac5b1/1/test-failed-1.png`
Trace: `webapp-artifacts/675853ad-c889-4e40-8c72-f6bd0ecac5b1/1/trace.zip`

### 2026-09-18 00:16 UTC — tests/t10_t12_lifecycle/test_t10_stop_mid_run.py::test_t10_stop_mid_run_ends_run_and_records_result

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:16:12 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:16:12 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 25 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-StopMidRun"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/3b04ea5f-d4d6-4707-b4bf-03f673c34e88/1/test-failed-1.png`
Trace: `webapp-artifacts/3b04ea5f-d4d6-4707-b4bf-03f673c34e88/1/trace.zip`

### 2026-09-18 00:18 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_dns_200mbps_128b.py::test_t10_t12_lifecycle_dns_200mbps_128b

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:17:58 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:17:58 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 25 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-DNS"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/6fa70c55-b379-4464-a73d-602445c23708/1/test-failed-1.png`
Trace: `webapp-artifacts/6fa70c55-b379-4464-a73d-602445c23708/1/trace.zip`

### 2026-09-18 00:18 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_icmp_5gbps_64b.py::test_t10_t12_lifecycle_icmp_5gbps_64b

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:18:29 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:18:29 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 25 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-ICMP"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/a1a2d844-28ae-4b78-8bb1-a5d3225caad3/1/test-failed-1.png`
Trace: `webapp-artifacts/a1a2d844-28ae-4b78-8bb1-a5d3225caad3/1/trace.zip`

### 2026-09-18 00:20 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps.py::test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:20:15 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:20:15 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- img
- 'heading "Statistics — T10-Life-Multi · UID: 16e7d013 16e7d0136e80449fa0ea5a199778677

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-Life-Multi', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '3', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '3', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.6.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '27'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.6.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '27'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.6.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.6.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="TCP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="TCP Edit TCP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '900', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="ICMP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="ICMP Edit ICMP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'td:nth-child(5) > .fc', 'expression': 'to.have.count', 'expectedNumber': 2, 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=1', 'value': '100', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=1', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="TCP Edit TCP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=button[name="ICMP Edit ICMP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '25', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key
...(truncated)
```
Screenshot: `webapp-artifacts/48d4f1c5-fa31-433b-9700-ee202ef052fc/1/test-failed-1.png`
Trace: `webapp-artifacts/48d4f1c5-fa31-433b-9700-ee202ef052fc/1/trace.zip`

### 2026-09-18 00:22 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_ntp_50mbps_90b.py::test_t10_t12_lifecycle_ntp_50mbps_90b

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:22:52 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:22:52 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 24.9

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-NTP"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-Life-NTP', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-Life-NTP"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> select >> nth=2', 'strict': True, 'options': [{'label': 'Mbps'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '50', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> select >> nth=2', 'strict': True, 'options': [{'label': 'Mbps'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '50', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.8.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '29'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.8.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '29'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.8.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.8.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="NTP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '4', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '20', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '4', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Por
...(truncated)
```
Screenshot: `webapp-artifacts/f36a18fb-88b8-4b36-b92c-6bf47d11da38/1/test-failed-1.png`
Trace: `webapp-artifacts/f36a18fb-88b8-4b36-b92c-6bf47d11da38/1/trace.zip`

### 2026-09-18 00:24 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_tcp_2gbps_512b.py::test_t10_t12_lifecycle_tcp_2gbps_512b

**Status:** pending review

Failure message: failed on teardown with "AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:24:08 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:24:08 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CP

Trace summary:
```
(no trace captured)
```

### 2026-09-18 00:27 UTC — tests/t10_t12_lifecycle/test_t10_two_testbeds_simultaneous.py::test_t10_two_testbeds_run_simultaneously

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:27:04 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:27:04 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- text: Model NTG10G4 10G SN 03000200-0400-0500-0006-000700080009 CPU
- img: 25%
- text: 25 %

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Concur-A"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Concur-B"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/7159664b-6330-4f8c-94de-ae31854996f3/1/test-failed-1.png`
Trace: `webapp-artifacts/7159664b-6330-4f8c-94de-ae31854996f3/1/trace.zip`

### 2026-09-18 00:28 UTC — tests/t10_t12_lifecycle/test_t10_unrelated_action_during_live_run.py::test_t10_unrelated_action_during_live_run

**Status:** pending review

Failure message: AssertionError: T10-LiveCtrl dropped out of ACTIVE state (Stats button gone) purely as a side effect of creating and deleting a completely unrelated, zero-port draft testbed elsewhere on the box — this test never touched T10-LiveCtrl itself after confirming it was live. This would be a materially BIGGER finding than the existing Edit/Clone-while-active bug: it would mean the scope of 'Confirmed product issues' needs to widen from 'a write referencing the specific live testbed' to 'any backend wr

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Unrelated"i'})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-LiveCtrl"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-LiveCtrl', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-LiveCtrl"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.22.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.22.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.22.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.22.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="UDP Edit UDP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '1500', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '90', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(3) > .fc > input', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(3) > .fc > input', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="Save"s]', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="Save"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="Start"s]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'timeout': 5000, 'strict': True})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'timeout': 8000, 'strict': True})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:text="Port Status"i', 'strict': True, 'timeout': 30000})
  Frame.expec
...(truncated)
```
Screenshot: `webapp-artifacts/bb5b29ae-4269-43b4-87cf-16e4453d7842/1/test-failed-1.png`
Trace: `webapp-artifacts/bb5b29ae-4269-43b4-87cf-16e4453d7842/1/trace.zip`

### 2026-09-18 00:29 UTC — tests/t10_t12_lifecycle/test_t12_run_history_and_exports.py::test_t12_run_history_exports_delete_and_reports_badge

**Status:** pending review

Failure message: AssertionError: Locator expected to be visible
Actual value: - img "Apposite Technologies"
- text: "Netropy Traffic Generator online Unit \"local\" — the traffic-generator unit this UI controls. Online: responding to health checks."
- img
- text: "Sep 17, 2026 17:29:48 UTC Unit clock NTP server: not configured (sandbox) Sep 17, 2026 17:29:48 UTC"
- button "Account": TU test User
- button "Menu":
  - img
- 'heading "T12-RunHistory · UID: 4797578d 4797578d80c44117ad78cda461957491" [level=1]':
  - 

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 403 (Forbidden)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T12-RunHistory"i'})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'internal:attr=[placeholder="e.g. web-perf-01"i]', 'value': 'T12-RunHistory', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Create draft"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': '.tb-tile >> internal:has-text="T12-RunHistory"i', 'expression': 'to.have.count', 'expectedNumber': 1, 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T12-RunHistory"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Ports"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.click({'selector': 'tr >> nth=1 >> .toggle .track', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'tr >> nth=2 >> .toggle .track', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'tr >> nth=1 >> input[placeholder="line rate"]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'tr >> nth=1 >> input[placeholder="line rate"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'tr >> nth=2 >> input[placeholder="line rate"]', 'value': '1', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'tr >> nth=2 >> input[placeholder="line rate"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="3 Streams"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name="✚ Add Stream"s]', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name="ICMP"s]', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="ICMP"s]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': '.pill >> internal:has-text="used"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'div >> internal:has-text="Disabled \\u2014 traffic runs at full rate"i >> nth=-1 >> .toggle .track', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fg >> internal:has-text="Ramp up"i >> input[type="number"]', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': '.fg >> internal:has-text="Ramp up"i >> input[type="number"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fg >> internal:has-text="Hold time"i >> input[type="number"]', 'value': '10', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': '.fg >> internal:has-text="Hold time"i >> input[type="number"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fg >> internal:has-text="Ramp down"i >> input[type="number"]', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': '.fg >> internal:has-text="Ramp down"i >> input[type="number"]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Start"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Continue"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Statistics"i]', 'expression': 'to.be.visible', 'timeout': 75000, 'isNot': False})  FAILED: Expect failed
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Discard"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.isVisible({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name="Port 1"i] >> internal:role=button[name="Release"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Deactivate & release"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name="Port 1"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})  FAILED: Expect failed
  Page.screenshot({'fullPage': False, 'type': 'png', 'timeout': 30000})

Non-2xx network responses:
  POST http://192.168.173.111:8080/ctrl/v1/units/local/ports/1/release -> 403 Forbidden
```
Screenshot: `webapp-artifacts/0763b57d-1363-4dc7-9acf-f2985647b3b6/1/test-failed-1.png`
Trace: `webapp-artifacts/0763b57d-1363-4dc7-9acf-f2985647b3b6/1/trace.zip`

### 2026-09-18 00:43 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_multistream_tcp_icmp_2gbps.py::test_t10_t12_lifecycle_multistream_tcp_icmp_2gbps

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator(".tb-tile").filter(has_text="T10-Life-Multi").get_by_role("button", name="Stats")

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  
...(truncated)
```
Screenshot: `webapp-artifacts/b5e04048-a257-4106-8288-50dc59d8228a/1/test-failed-1.png`
Trace: `webapp-artifacts/b5e04048-a257-4106-8288-50dc59d8228a/1/trace.zip`

### 2026-09-18 18:06 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_multistream_tcp_icmp_2gbps.py::test_t10_t12_lifecycle_multistream_tcp_icmp_2gbps

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator(".tb-tile").filter(has_text="T10-Life-Multi").get_by_role("button", name="Stats")

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Page error (JS exception): V.dispatchAction is not a function
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-Life-Multi', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.6.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '27'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.6.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '27'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.6.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.6.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="TCP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="TCP Edit TCP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '900', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="ICMP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="ICMP Edit ICMP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'td:nth-child(5) > .fc', 'expression': 'to.have.count', 'expectedNumber': 2, 'timeout': 10000, 'isNot': False})
...(truncated)
```
Screenshot: `webapp-artifacts/3c414d66-7e4f-46cb-8968-2a72fcfb5e18/1/test-failed-1.png`
Trace: `webapp-artifacts/3c414d66-7e4f-46cb-8968-2a72fcfb5e18/1/trace.zip`

### 2026-09-18 18:08 UTC — tests/t10_t12_lifecycle/test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps.py::test_t10_t12_lifecycle_multistream_tcp_icmp_3gbps

**Status:** pending review

Failure message: playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator(".tb-tile").filter(has_text="T10-Life-Multi").get_by_role("button", name="Stats")

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i'})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 3"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 3"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Available"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=row[name="Port 4"i] >> internal:role=button[name="Reserve"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=row[name="Port 4"i] >> internal:text="Reserved"s', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="e.g. web-perf-"i]', 'value': 'T10-Life-Multi', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="Create draft"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': '.tb-tile >> internal:has-text="T10-Life-Multi"i >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(3) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'tr:nth-child(4) > td > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '3', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'value': '3', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'internal:role=row[name=/^Port 4\\b/] >> internal:attr=[placeholder="line rate"i]', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="2 Network Configuration per-"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=0', 'value': '10.0.6.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': '.seg >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '27'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="10.1.0.10"i] >> nth=1', 'value': '10.0.6.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.selectOption({'selector': 'div:nth-child(2) > div:nth-child(2) > .ne-src > .ne-src-main > div > div:nth-child(2) > .ne-combo > select', 'strict': True, 'options': [{'valueOrLabel': '27'}], 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=2', 'value': '10.0.6.1', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'internal:role=textbox[name="auto"i] >> nth=0', 'value': '10.0.6.2', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="3 Streams traffic flows — at"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="TCP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="TCP Edit TCP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=0', 'value': '900', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=0', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="✚ Add Stream"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'internal:role=button[name="ICMP"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.isVisible({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Add stream"s]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="ICMP Edit ICMP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'td:nth-child(5) > .fc', 'expression': 'to.have.count', 'expectedNumber': 2, 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'td:nth-child(5) > .fc >> nth=1', 'value': '100', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'td:nth-child(5) > .fc >> nth=1', 'key': 'Enter', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.expect({'selector': 'internal:role=button[name="TCP Edit TCP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': 'internal:role=button[name="ICMP Edit ICMP"i] >> nth=0', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': 'internal:role=button[name="4 Traffic and Load Profile"i]', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.click({'selector': 'div:nth-child(2) > div > .toggle > .track', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.queryCount({'selector': '.fc > input >> nth=0'})
  Frame.isVisible({'selector': '.fc > input >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': '.fc > input >> nth=0', 'value': '5', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.fill({'selector': 'div:nth-child(2) > .fc > input', 'value': '25', 'strict': True, 'timeout': 30000})
  Frame.waitForTimeout({'waitTimeout': 400})
  Frame.press({'selector': 'div:nth-child(2) > .fc > input', 'key
...(truncated)
```
Screenshot: `webapp-artifacts/2640bca4-a265-477e-b4f4-da4732e574f4/1/test-failed-1.png`
Trace: `webapp-artifacts/2640bca4-a265-477e-b4f4-da4732e574f4/1/trace.zip`

### 2026-10-06 03:18 UTC — tests/t15_wan_emulator/test_t15_delay_only.py::test_t15_delay_only_adds_expected_latency

**Status:** pending review

Failure message: failed on setup with "playwright._impl._errors.TimeoutError: Page.goto: Timeout 30000ms exceeded.
Call log:
  - navigating to "http://192.168.173.89/", waiting until "load""

Trace summary:
```
(no trace captured)
```

### 2026-10-13 06:28 UTC — tests/t15_wan_emulator/test_t15_asymmetric_delay.py::test_t15_asymmetric_delay_reported_per_direction

**Status:** pending review

Failure message: AssertionError: Traffic never started after Start → Continue. On-screen toasts: []
Unit healthy; Controller view: {'health': {'status': 'ok', 'demo': False, 'recovery': False, 'units': {'local': True}}, 'datapath': None, 'latest_run': None}

Trace summary:
```
Page error (JS exception): Failed to read the 'sessionStorage' property from 'Window': Access is denied for this document.
Console error: Failed to load resource: the server responded with a status of 504 (Gateway Timeout)
Console error: Failed to load resource: the server responded with a status of 409 (Conflict)
Action sequence:
  BrowserContext.newPage({})
  Frame.goto({'url': '/', 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 10000, 'isNot': False})
  Frame.expect({'selector': '.card >> internal:has-text="Testbeds"i >> internal:text=/^\\d+ saved · \\d+ active$/', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.queryCount({'selector': '.modal-overlay'})
  Frame.queryCount({'selector': '.toast button'})
  Frame.isVisible({'selector': 'internal:role=button[name="← Dashboard"i]', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:text="Port Status"i', 'strict': True, 'timeout': 30000})
  Frame.isVisible({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:text="Port Status"i', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.expect({'selector': '.card >> internal:has-text="Testbeds"i >> internal:text=/^\\d+ saved · \\d+ active$/', 'expression': 'to.be.visible', 'timeout': 20000, 'isNot': False})
  Frame.queryCount({'selector': '.tb-tile >> internal:has="internal:text=\\"T15-WAN\\"s"'})
  Frame.click({'selector': 'internal:role=button[name="✚ Create Testbed"s]', 'strict': True, 'timeout': 30000})
  Frame.fill({'selector': 'internal:attr=[placeholder="e.g. web-perf-01"i]', 'value': 'T15-WAN', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Traffic Engine"s]', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name="Create draft"s]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': '.tb-tile >> internal:has="internal:text=\\"T15-WAN\\"s"', 'expression': 'to.have.count', 'expectedNumber': 1, 'timeout': 10000, 'isNot': False})
  Frame.click({'selector': '.tb-tile >> internal:has="internal:text=\\"T15-WAN\\"s" >> internal:role=button[name="Edit"i]', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=heading[name="Ports"i]', 'expression': 'to.be.visible', 'timeout': 15000, 'isNot': False})
  Frame.getAttribute({'selector': 'internal:role=button[name=/^1 /] >> nth=0', 'name': 'aria-expanded', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name=/^1 /] >> nth=0', 'expression': 'to.have.attribute.value', 'expressionArg': 'aria-expanded', 'expectedText': [{'string': 'true', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.isChecked({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=checkbox >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=checkbox >> nth=0 >> xpath=..', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=checkbox >> nth=0', 'expression': 'to.be.checked', 'timeout': 10000, 'expectedValue': {'value': {'o': [{'k': 'checked', 'v': {'b': True}}], 'id': 1}, 'handles': []}, 'isNot': False})
  Frame.isChecked({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=checkbox >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=checkbox >> nth=0 >> xpath=..', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=checkbox >> nth=0', 'expression': 'to.be.checked', 'timeout': 10000, 'expectedValue': {'value': {'o': [{'k': 'checked', 'v': {'b': True}}], 'id': 1}, 'handles': []}, 'isNot': False})
  Frame.selectOption({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=combobox >> nth=-1', 'strict': True, 'options': [{'valueOrLabel': 'Mbps'}], 'timeout': 30000})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=spinbutton', 'value': '500', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=spinbutton', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name=/^Port\\ 3\\b/] >> internal:role=spinbutton', 'expression': 'to.have.value', 'expectedText': [{'string': '500', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.selectOption({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=combobox >> nth=-1', 'strict': True, 'options': [{'valueOrLabel': 'Mbps'}], 'timeout': 30000})
  Frame.fill({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=spinbutton', 'value': '500', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=spinbutton', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name=/^Port\\ 4\\b/] >> internal:role=spinbutton', 'expression': 'to.have.value', 'expectedText': [{'string': '500', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.getAttribute({'selector': 'internal:role=button[name=/^2 /] >> nth=0', 'name': 'aria-expanded', 'strict': True, 'timeout': 30000})
  Frame.click({'selector': 'internal:role=button[name=/^2 /] >> nth=0', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name=/^2 /] >> nth=0', 'expression': 'to.have.attribute.value', 'expressionArg': 'aria-expanded', 'expectedText': [{'string': 'true', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'internal:role=row[name=/^3\\s/] >> internal:role=textbox[name="10.1.0.10"i]', 'value': '10.0.0.1', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'internal:role=row[name=/^3\\s/] >> internal:role=textbox[name="10.1.0.10"i]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.selectOption({'selector': 'internal:role=row[name=/^3\\s/] >> internal:role=combobox >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name=/^3\\s/] >> internal:role=textbox[name="10.1.0.10"i]', 'expression': 'to.have.value', 'expectedText': [{'string': '10.0.0.1', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.getAttribute({'selector': 'internal:role=button[name=/^2 /] >> nth=0', 'name': 'aria-expanded', 'strict': True, 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=button[name=/^2 /] >> nth=0', 'expression': 'to.have.attribute.value', 'expressionArg': 'aria-expanded', 'expectedText': [{'string': 'true', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.fill({'selector': 'internal:role=row[name=/^4\\s/] >> internal:role=textbox[name="10.1.0.10"i]', 'value': '10.0.0.2', 'strict': True, 'timeout': 30000})
  Frame.press({'selector': 'internal:role=row[name=/^4\\s/] >> internal:role=textbox[name="10.1.0.10"i]', 'key': 'Tab', 'strict': True, 'timeout': 30000})
  Frame.selectOption({'selector': 'internal:role=row[name=/^4\\s/] >> internal:role=combobox >> nth=0', 'strict': True, 'options': [{'valueOrLabel': '25'}], 'timeout': 30000})
  Frame.expect({'selector': 'internal:role=row[name=/^4\\s/] >> internal:role=textbox[name="10.1.0.10"i]', 'expression': 'to.have.value', 'expectedText': [{'string': '10.0.0.2', 'matchSubstring': False, 'normalizeWhiteSpace': False}], 'timeout': 10000, 'isNot': False})
  Frame.getAttribute({'selector': 'internal:role=button[name
...(truncated)
```
Screenshot: `webapp-artifacts/1508f15f-3f8d-462a-a788-a054f8e590c3/1/test-failed-1.png`
Trace: `webapp-artifacts/1508f15f-3f8d-462a-a788-a054f8e590c3/1/trace.zip`

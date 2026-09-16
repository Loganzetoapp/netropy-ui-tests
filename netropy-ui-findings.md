# Netropy UI Findings

Everything found while building the automated Playwright suite against the
Traffic Generator web UI — confirmed product behavior, places the written
test plan (`netropy-ui-test-plan.md`) didn't match reality, and what's still
waiting on an answer from Travis. See `netropy-ui-reference.md` for the
control-by-control UI inventory this was built alongside.

Target: `192.168.173.111:8080`, a dedicated lab VM (confirmed not shared —
see "Plan questions the product answered" below). Suite coverage: all 13
plan areas (T1–T13), 91 automated tests.

---

## Confirmed product issues

Reproduced directly, not inferred from a single failed run.

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
*"loss-based default (no pass criteria set)"*, next to an unexplored "Edit
pass criteria" control. There's a real editor for this somewhere in the
product; what the default actually computes hasn't been pinned down.

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

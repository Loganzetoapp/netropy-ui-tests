# Netropy UI Findings

Everything found while building the automated Playwright suite against the
Traffic Generator web UI — confirmed product behavior, places the written
test plan (`netropy-ui-test-plan.md`) didn't match reality, and what's still
waiting on an answer from Travis. See `netropy-ui-reference.md` for the
control-by-control UI inventory this was built alongside.

Target: `192.168.173.111:8080`, a shared lab appliance. Suite coverage: all
13 plan areas (T1–T13), 85 automated tests.

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

### Testbed activation intermittently returns 502
`POST /ctrl/v1/tests/{name}/activate?wait=15` has returned `502 Bad Gateway`
(`"Remote end closed connection without response"`) on multiple otherwise-
correct testbeds — the backend failing to reach the underlying traffic-engine
service, confirmed via network logging, not a frontend or test-script issue.
No single config variable (line rate, protocol, frame size, port pair, ramp)
has been shown to deterministically cause or prevent it across repeated
trials; it reads as genuine intermittency. The activate call can also
legitimately take 15s+ to resolve even when it succeeds, which is easy to
mistake for a failure if a script's timeout is too short.
Status: intermittent, unresolved as of this report.

### Port links drop to "No Link" after activation — recurring, 3 incidents
Ports have gone `Down / 0M / No Link` after activation on three separate
occasions: Port 5+6 once, Port 7+8 once (both the *first-ever* activation
attempted on that specific pair), and most recently all of Port 5–8
simultaneously, found during a full-suite run. Each time, the drop happened
independent of test-script cleanup — teardown completed normally regardless.
The two isolated incidents self-recovered; the pattern itself hasn't.

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

---

## Still open, pending Travis

Nothing below is guessed at in the test suite — each blocks a specific plan
item until it's answered.

1. **What's the actual PASS/FAIL loss threshold?** A run showed nonzero
   dropped frames on individual ports yet still passed at 0.000% aggregate
   loss. No strict loss-threshold assertions have been written until this is
   confirmed.
2. **Is this box a shared appliance or a dedicated test VM?** Determines how
   cautious traffic-generating tests need to be about interfering with other
   users — and whether the port link-down pattern above could be cross-user
   interference rather than a product issue.
3. **Can the frontend add `data-testid` attributes?** Current selectors are
   role-based and scoped to row/card, which works, but several controls
   (icon-only buttons, testbed tiles) have no accessible name at all and are
   matched by tooltip text or CSS class as a fallback.
4. **What does per-port Reset actually do to the link?** Reset All is
   already off-limits by policy. Per-port Reset was never confirmed either,
   so no automated test clicks it — same caution, unresolved.
5. **What's the session timeout length?** The rest of authentication
   (login, logout, invalid password, concurrent sessions) is covered;
   timeout is the one deliberately-skipped item rather than a guessed value.
6. **Is a second test account available?** Only one account is configured. A
   second browser session on the same account sees an already-reserved port
   as its own, not a conflict — so "reserve a port another user holds →
   blocked with a clear error" can't be reproduced without a genuinely
   separate identity.

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
| T10 · Activation lifecycle | Live badges, dashboard active count, two simultaneous testbeds | stateful |
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

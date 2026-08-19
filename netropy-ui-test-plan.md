# Netropy Traffic Generator 4.0 — UI Test Plan (Playwright)

Author: Logan · Draft for review by Travis
Target: Netropy Traffic Generation 4.0 browser UI
Tooling: Microsoft Playwright (TypeScript)

---

## 1. Scope and approach

This plan covers automated UI testing of the Netropy 4.0 web interface: dashboard, port management, testbed configuration wizard (Traffic Engine), test execution, live statistics, and reports.

Out of scope for now:
- Connectivity Diagnostics section (marked Work In Progress in the UI — will churn)
- Traffic correctness itself (packet-level validation is the product's job, not the UI suite's)
- Other apps (RFC 2544, SessionStrike) until licensed
- Firmware/admin operations against shared hardware

### Two test classes

**Class A — Hardware-free (fast, run on every commit).** Validation rules, computed values, view toggles, form behavior. These exercise pure UI logic and never start traffic. They can run in parallel and should make up ~80% of the suite.

**Class B — Stateful (slower, run nightly or on demand).** Activation, live stats, stop/complete, report generation. These generate real traffic on the box, must run serially, and need exclusive port ownership.

Tag tests `@hardware-free` / `@stateful` and split them into separate Playwright projects so CI can run Class A on every commit and Class B on a schedule.

### Suite architecture

- **Auth setup project**: log in once, save storageState, reuse across all tests.
- **API-first fixtures**: use the RESTful API for setup/teardown (create/delete testbeds, reserve/release ports) so Playwright only tests the UI behavior under test. Confirm API docs/access with Travis.
- **Global port hygiene**: a fixture that releases all ports and stops any live test before and after each Class B test. Port state is global on the box — without this the suite deadlocks itself.
- **Selector strategy**: role-based selectors scoped to rows/cards (`getByRole('row', { name: 'Port 4' })`). Request `data-testid` attributes from the frontend team for testbed cards and wizard sections.
- **Timing**: never assert against the live UTC clock, uptime counter, or elapsed-time badges. Mask them in any visual comparisons. Use `expect.poll` / web-first assertions instead of fixed waits wherever possible.

---

## 2. Test areas

### T1 — Authentication and session (Class A) — P0
- Valid login lands on dashboard
- Invalid password shows error, no session
- Logout returns to login and kills the session (back button doesn't restore)
- Session timeout behavior (confirm timeout length first)
- Two concurrent sessions for the same user both work (collaboration is a marketed feature)

### T2 — Dashboard smoke (Class A) — P0
- System header renders model, serial, CPU/memory/disk/load/uptime
- Port Status table renders 8 rows; "8/8 links up" badge matches row states
- Testbeds counter ("N saved · N active") matches the cards shown
- Licenses section shows Traffic Engine LICENSED; RFC 2544 and SessionStrike NOT LICENSED
- Grid/list view toggle switches rendering; check whether choice persists across reload (assert whichever behavior is intended)

### T3 — Port management (Class A where possible) — P0
- Reserve a port → status changes, Reserved By shows current user
- Release a port → returns to Available
- Reserve a port already held by another session → blocked with clear error (needs second storageState)
- Reserved By / Test Name columns populate correctly while a testbed is active (Class B)
- Per-port reset and Reset All behavior (confirm what "reset" does before automating against shared hardware)

### T4 — Testbed lifecycle (Class A) — P0
- Create testbed: name + app type → card appears, counter increments
- Validation: empty name, duplicate name
- Rename via Edit; changes persist after reload
- Duplicate (copy icon): new card with distinct UID
- Delete from card and from inside Edit → card gone, counter decrements
- Copy-UID button puts the UID on the clipboard
- Export (download icon) produces a file; Import round-trips it: export → delete → import → config identical
- Import malformed/truncated file → clear error, no broken card
- License gating: creating an RFC 2544 or SessionStrike testbed is blocked or hidden while unlicensed

### T5 — Wizard step 1: Ports (Class A) — P0
- Stepper shows red ✕ on invalid step, clears when fixed (known trigger: bidirectional port with Peer Port = none)
- USE toggle enables/disables the row's controls
- Toggling a configured port off then on: document and assert whether config clears or is remembered
- Peer port options exclude self; document valid pairings
- Line rate validation: 0, negative, above max (10), non-numeric; unit dropdown behavior
- Network profile dropdown + "Save as a new profile…" (see T9)
- Roster/Topology view toggle renders both views

### T6 — Wizard step 2: Network Configuration (Class A) — P0
Highest-value hardware-free area: the UI computes values live.
- Host count math: /32 → 1 host, /31 → 2 hosts, /25 → 126 clients, /24, etc. Assert both the circle badge and the inline "x.x.x.x → y.y.y.y (N hosts)" text
- IP Inc interacts with host count correctly
- Invalid inputs: malformed IP, out-of-range octet, bad MAC format
- MAC auto-link: chain icon links Port A's Dest MAC to Port B's Source MAC — change source, assert peer's dest follows; toggle the link off, assert it stops following
- Gateway vs Dest MAC segmented toggle swaps input; assert whether the hidden value is preserved or cleared
- Cards/Table view toggle: edit in one view, value shows in the other
- Encap dropdown options render (None + whatever VLAN options exist)

### T7 — Wizard step 3: Streams (Class A) — P0
- Add Stream → new row, name auto-generated
- Delete streams down to zero → step 3 flags invalid ("at least one is required to activate"), Activate disabled
- Duplicate stream → distinct copy, name increments
- Frame size: "Apply to all" overwrites per-row values; per-row edit sticks until next apply-to-all
- Frame size bounds: below 64, jumbo max (confirm limit), non-numeric
- Distribute across ports: All Ports / Alternate / Sequence — document behavior, assert Interface Port ID assignment per mode
- Layer chips (Ethernet/IPv4/UDP/Payload) open their editors — map this sub-surface when first automating (not yet screenshotted)
- Enable/disable state per stream persists

### T8 — Wizard step 4: Traffic and Load Profile (Class A) — P0
- Stream mix must total 100%: assert USED/REMAINING readout; document behavior when over/under (block vs warn vs rebalance)
- Edit-all vs inline pencil edits
- Unit toggle %/Gbps/Mbps/bps converts values rather than clearing them
- Per-port selector switches the donut to that port's mix
- Ramp math: change ramp-up/hold/ramp-down, assert the "a + b + c = total" line and the Total Duration badge update; change units (sec dropdown)
- Ramp enabled off → assert replacement state (constant load)
- Iterations: 0, negative, large; total duration scales with iterations
- TX burst: empty = datapath default (placeholder behavior), 1, 32; bandwidth cap accepts blank = line rate

### T9 — Network Profiles (Class A) — P1
- Empty state renders with "create one" prompt
- Save current port config as a profile from the wizard; profile appears on dashboard
- Select profile in a new testbed → fields populate
- Export all / import round-trip; export-all with zero profiles (document behavior)
- Profile referencing a port that's reserved elsewhere: document and assert behavior

### T10 — Activation and run lifecycle (Class B) — P0
- Activate with valid config → navigates to Statistics page, badges flip to ACTIVE + LIVE with elapsed timer
- Activate is disabled while any wizard step is invalid
- Live run: duration counts toward configured total (e.g. 0:25 / 0:50); KPI cards populate; per-port table shows non-zero Tx/Rx
- Stop mid-run → run ends, result recorded
- Natural completion after ramp (50s config): end state recorded as "completed", new run row appears with PASS/FAIL
- Dashboard during a run: testbed counter shows "1 active", port table shows Reserved By / Test Name for in-use ports, card state changes
- After completion: does the testbed auto-deactivate? (observed end reason "completed" — assert the intended behavior once confirmed)
- Two testbeds running simultaneously on disjoint ports

### T11 — Live statistics view (Class B for live; some checks possible on historical data) — P1
- Metric tabs: Throughput / Packet Rate / Latency / Frame Loss / Jitter each render
- Aggregate vs Per Stream toggle
- Scope (All Ports / Average / per-port) and Signal (Both/Tx/Rx) filter the series shown
- Unit toggle Auto/Gbps/Mbps/bps re-labels axis
- Zoom (1.2M/Full) and range slider function; hover tooltip shows per-series values
- Per-Port Aggregate Statistics: Columns picker adds/removes columns
- Stream Statistics: Total / Per Port / Per Direction views; rows-per-page and pagination
- Dropped-frame highlighting (red) appears when drops occur

### T12 — Reports and exports (Class B to generate; Class A to verify existing) — P0
- Run history table: each run shows started-at, duration, avg TX/RX, loss %, result
- Each export format downloads: PDF, XLSX, CSV, JSON, ZIP; filename matches `<testbed>-<runId>.<ext>`
- JSON export parses and contains expected keys (config snapshot, aggregate stats, per-stream stats) — prefer asserting numbers here over scraping the UI
- PDF sanity: non-zero size, page count, PASS/FAIL badge present (text-extract check)
- Delete a run → row gone, Reports badge count on dashboard card decrements
- Reports badge on the dashboard card opens the run history
- PASS threshold: live view showed 32 dropped frames yet the run PASSed at 0.000% loss — confirm the pass/fail rule with the team and encode it as an assertion

### T13 — Deferred: Connectivity Diagnostics
Marked WORK IN PROGRESS in the UI. Only test now: DHCP Pre-Acq renders as not supported/disabled. Revisit when the feature stabilizes. ARP/Ping/Traceroute are live network actions — they belong in an integration tier, not the UI suite.

---

## 3. Rollout phases

**Phase 1 (now):** Auth setup + T1, T2, T4 create/delete, T5/T6 validation math. All Class A. Proves the harness and catches regressions in the highest-traffic screens.

**Phase 2:** Rest of the wizard (T7, T8), T3 reservation, T9 profiles, license gating. Still hardware-free except reservation.

**Phase 3:** Class B lifecycle (T10, T12) as a serial nightly project with the port-hygiene fixture.

**Phase 4:** T11 stats-view details, second-user concurrency tests, visual regression with masked dynamic regions.

## 4. Open questions for Travis

1. Is there REST API documentation / an API token for test setup and teardown?
2. Shared appliance or dedicated VM for CI? (Determines how aggressive Class B can be and whether Reset All is safe to automate.)
3. What is the PASS loss threshold?
4. Can the frontend team add `data-testid` attributes to testbed cards and wizard sections?
5. Intended behavior for: grid/list persistence, port-config retention after toggle-off, over-100% traffic mix, auto-deactivate after completion.

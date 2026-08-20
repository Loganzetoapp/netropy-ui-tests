# Netropy 4.0 UI Reference

A control-by-control inventory of the Netropy Traffic Generator web UI, built by
clicking through the app. This exists to speed up writing role-based Playwright
selectors for new tests — it's not a test plan (see `netropy-ui-test-plan.md`
for that) and it doesn't cover *why* each area matters.

Compiled against the live box, chromium, logged in as `test`.

---

## Top bar

Present on every screen.

- **Account button** (avatar + name/"User", top right area) — opens a **modal**
  (not a dropdown), with:
  - Testbeds count / Ports reserved count (two stat tiles)
  - **Account**: "Change password" (currently shows a `SOON` badge — disabled),
    "Back up testbeds" (downloads a file — chevron `>` suggests a sub-view)
  - **Customization**: Dark mode toggle, "Hide dashboard system & status" toggle
  - **Accessibility**: High contrast toggle
  - Modal has a fixed height with no internal scroll; closes via the `×` button
    top-right.
- **Menu button** (gear icon, far top-right) — opens a **dropdown** (distinct
  from the Account modal above), with: Dark mode, About, Help, Settings,
  **Sign out**. This is where logout actually lives, not the Account modal.
  - Caveat: in the accessibility tree these menu items render as unlabeled
    `<button>` elements (icon + text) — `get_by_role("button", name=...)`
    still resolves them by visible text fine in Playwright, this is just a
    quirk of some lightweight inspection tools.
- Header also shows: system status dot ("online"), current UTC clock (never
  assert on this — see CLAUDE.md), and on the dashboard specifically, "←
  Dashboard" / testbed name breadcrumbs when inside a testbed or Statistics
  view.

## Dashboard — Port Status table

Columns: PORT, LINK, SPEED, MAC ADDRESS, STATUS, RESERVED BY, TEST NAME,
RESERVE, RESET.

- **Reserve/Release button** — toggles per row. Reserving fires
  `POST /ctrl/v1/units/local/ports/{n}/reserve`, flips STATUS to `Reserved`
  (red/orange text), RESERVED BY to `<username> (you)`, shows a toast ("Port N
  reserved."), and the button becomes "Release" with tooltip "Release the
  reservation". Releasing is the mirror (toast "Port N released.").
- **Per-port Reset button** (circular arrow icon) — exists but its effect
  against shared hardware is unconfirmed; not exercised here.
- **"Reset All"** button (top right of the section) — exists but never
  automate this; effect on shared hardware unconfirmed.
- Table rows are addressable via `get_by_role("row", name="Port N")` — the
  accessible name is a concatenation of the whole row's cell text, so
  substring matching on "Port N" works and is already used elsewhere in this
  repo (`test_smoke.py`, `test_t3_port_management.py`).

## Network Profiles section

- Empty state: "No network profiles yet — **+ Create one.**"
- **Import** button, **Export all** button (downloads), **+ Create Network
  Profile** button — not exercised (network profile creation is T9, out of
  scope for this pass).

## Testbeds section

Header shows "N saved · N active" and a **grid/list view toggle** (two small
icon buttons). Both views expose the same actions, just laid out differently:

- **Grid (card) view**: each card has — testbed icon, name, module type
  ("Traffic Engine"), a small download icon, a duplicate/copy icon, a red
  trash (delete) icon, `UID: <short-uid>` with its own copy-to-clipboard icon,
  "Linerate: X · Streams: N", a "Reports: N" button, and **Activate** /
  **Edit** buttons at the bottom.
- **List (table) view**: columns NAME, FEATURE, STATE, UID, LINERATE,
  STREAMS, REPORTS, ACTIONS (Activate, Edit, download, duplicate, delete).
- **Activate is disabled** (greyed out) when the testbed has no configured
  line rate (e.g. a draft with no ports enabled yet) — observed on `TE-01`
  which has `Linerate: —`. Don't assume Activate is always clickable; check
  STATE/LINERATE first.
- **+ Create Testbed** button opens a modal: testbed name field, a module
  picker grid (Traffic Engine is the only unlocked tile in this license;
  RFC 2544, Session Strike, AppPlayback, RFC 9411, DDoS Storm, DNS Storm,
  VoIP/SIP, OTT Video, ThreatStorm, PQC are all shown with a lock icon and are
  unclickable — matches the license gating noted in the plan's T4 section),
  Cancel / **Create draft** buttons. Creating a draft immediately shows a
  toast ("Saved draft \"<name>\" (inactive).") and adds a card/row with STATE
  `INACTIVE`.
- **Delete** shows a confirmation modal: "Delete testbed — Remove
  **\<name\>** from the unit? The configuration is not recoverable." with
  Cancel / Delete buttons. Confirms via toast ("Deleted \"<name>\".").
- **Reports button** on a card navigates to `Statistics — <name>` (see below),
  not a download by itself.

## The 4-step wizard (Edit → per-testbed configuration page)

Not a modal — it's a single scrollable page with an accordion/stepper, one
section expanded at a time. Header shows testbed name, UID (with copy icon),
module type, STATE badge, and an `UNSAVED` badge once anything changes. A
"← Dashboard" button returns to the main screen. Bottom bar (always visible):
**Discard Changes**, **Delete**, **Save**, **Apply** (Apply activates the
testbed — stays disabled until the config is valid, e.g. at least 1 stream
and ports configured).

### Step 1 — Ports
- **Roster / Topology** view toggle (top right), plus a chevron to
  collapse/expand the whole step.
- Roster (table) view columns: USE (toggle), PORT, MAX RATE, STATUS,
  MULTISITE (checkbox), DIRECTION (`bidirectional` / `tx only` / `rx only`),
  PEER PORT (`— none —` plus every *other* port — confirms peer options
  exclude self), LINE RATE (number input + unit select `Gbps`/`Mbps`/`Kbps`).
- Toggling USE on for a port makes that row's other controls interactive
  (they're disabled/greyed while USE is off) and adds a "Save as a new
  profile…" button next to the Network profile dropdown.
- **Validation example observed**: enabling exactly one port and trying to
  proceed shows a tooltip: *"a single-port testbed must be multisite — or add
  a second port to continue"* — blocks progress until you either check
  Multisite or enable a second port.
- Topology view: draws each enabled port as a card (IP, MAX rate badge, a
  Peer dropdown, TX&RX/TX/RX segmented buttons, line rate + unit, an × to
  remove) with arrows into a "DUT" node on the right. Has its own **+ Add
  Port** / **Select Ports…** buttons and a **Next →** button.

### Step 2 — Network Configuration
- **Cards / Table** view toggle, plus its own Network profile dropdown +
  "Save as a new profile…".
- Per enabled port, a card with:
  - **Source IP**: IP assignment (`Custom`/`Random`), IP/CIDR/Mask fields
    (CIDR select offers `/25`–`/32`), a live "N HOSTS" circle badge, IP Inc
    field, and inline hint text like `10.0.0.2 (1 host)`.
  - **Source MAC**: MAC assignment (`Custom`/`Random`/`Per-stream`), Base MAC,
    MAC Inc.
  - **Destination**: DST IP field with a chain-link **auto-fill button**
    ("Auto-fill from N src-ip") that pulls the peer port's source IP; a
    Gateway/Dest MAC segmented toggle (tabs) for "Next hop", each with its own
    auto-fill-from-peer button ("Auto-fill from N src-mac").
  - **Tagging**: Encap select — `None` / `VLAN` / `QinQ`.
- With 2 ports enabled and peered, Port 1's Dest IP auto-populated to Port 2's
  Source IP and vice versa — the auto-link behavior appears to fire
  automatically once ports are peered, not just on manual button click.

### Step 3 — Streams
- Empty state: "No streams yet — the testbed can be saved as a draft, but
  applying requires at least one." + **+ Add Stream** button.
- **Add Stream modal**: a protocol list on the left (grouped: IPv4 —
  UDP/TCP/ICMP; IPv6 — UDP(IPv6)/TCP(IPv6)/ICMPv6; Application —
  HTTP/HTTPS/DNS/NTP, HTTP and HTTPS tagged `WIP`; VoIP — SIP/RTP, both
  tagged `WIP`), a search-protocols box, a Name-prefix field ("prefix when
  adding several"), a Quantity field, and a detail panel on the right (title,
  description, LAYER STACK chips, default ports, a "WILL CREATE" preview of
  the resulting stream name(s)). Cancel / **Add stream**.
- Once added, streams render as a table: NAME (editable), INTERFACE PORT ID
  (dropdown: `All ports` + each individual port), LAYERS (chips: e.g.
  Ethernet/IPv4/UDP/Payload — plan notes these open a sub-editor, not yet
  mapped here), STATE (`enabled`/toggle), FRAME SIZE (number input), plus
  duplicate and delete icons per row.
- Section-level controls above the table: **FRAME SIZE — APPLY TO ALL** (input
  + "Apply to all" button) and **DISTRIBUTE ACROSS PORTS** (`All Ports` /
  `Alternate` / `Sequence` buttons).

### Step 4 — Traffic and Load Profile
- **Traffic Profile** (left): a per-port selector dropdown, a unit toggle
  (`%` / `Gbps` / `Mbps` / `bps`), a donut chart (center shows stream count),
  a legend list of streams with their % share and an inline pencil edit icon
  per stream, a USED/REMAINING readout, and an **Edit all** button.
- **Load Profile** (right): starts as a single toggle — "Disabled — traffic
  runs at full rate". Enabling it ("Ramp enabled") reveals:
  - An **Iterations** field and a **Total Duration** badge (e.g. "1m 20s").
  - A ramp graph (0 → 100% → 100% → 0, i.e. trapezoid) with draggable-looking
    points labeled ramp up / hold / ramp down.
  - **Ramp up / Hold time / Ramp down** number fields, each with a `sec` unit
    dropdown, plus a live formula line: "Total run time = ramp-up + hold +
    ramp-down = 10 + 60 + 10 = 80s".
- **Burst & Rate — applies to all ports** (below Traffic Profile): **TX burst
  (packets)** field (placeholder "1 — blank = datapath default", with hint
  text about small frames needing a larger batch to reach line rate) and
  **Bandwidth cap (Gbps)** field (placeholder "line rate" = blank means
  uncapped).
- A collapsed **"Connectivity diagnostics"** sub-section, tagged `WORK IN
  PROGRESS` — matches the plan's T13 deferred note; don't build tests against
  it yet.

## Statistics / Reports view

Reached via a testbed card's "Reports: N" button, or presumably after
Activate. URL pattern not recorded; navigated via in-app button only.

Header: "Statistics — \<name\>" with UID, module type, STATE badge, "←
Dashboard" and "✎ Edit" buttons.

**Test Reports** panel (collapsible via a "hide" link):
- Columns: RUN (e.g. `#6`, latest tagged `LATEST`), STARTED AT, DURATION
  (with an end-reason chip like `MANUAL STOP`), TOTAL TEST TIME, AVG TX, AVG
  RX, LOSS %, RESULT (`PASS`/presumably `FAIL`, plus a small circular info
  icon), REPORT (five export-format buttons per row: **PDF XLSX CSV JSON
  ZIP** — all downloads, not exercised here), DELETE (trash icon per row).
- Pagination: Rows-per-page `5`/`10`/`25`/`All`, "Showing 1–5 of N", page
  arrows.
- Below the table, when the testbed isn't currently active: an empty-state
  panel — "Testbed not active — Activate this testbed from its configuration
  page to collect statistics." This is presumably where live metric
  tabs/charts (Throughput, Packet Rate, Latency, Frame Loss, Jitter — per the
  plan's T11) render instead, once a run is live; not confirmed in this pass
  since Activate was never clicked.
- Every observed report row showed `0.000 %` loss regardless of duration —
  consistent with the existing open question about the real PASS/FAIL loss
  threshold/rounding (see `netropy-ui-test-plan.md`).

## Not covered in this pass

- Anything behind **Activate** (live Statistics charts, KPI cards, run
  completion flow) — deliberately not triggered; real traffic generation is
  out of scope for a documentation-only pass.
- Any download (Export all, per-testbed export icon, Back up testbeds, PDF/
  XLSX/CSV/JSON/ZIP report exports) — buttons noted by label only, not
  clicked.
- Per-port Reset and dashboard Reset All — noted by label only, per the
  standing safety rule against automating them.
- Network Profile creation flow, and Import/Export round-trip for both
  testbeds and profiles.
- The Streams step's per-layer editors (clicking a layer chip like
  "Ethernet"/"UDP" — mentioned in the plan as not yet mapped).

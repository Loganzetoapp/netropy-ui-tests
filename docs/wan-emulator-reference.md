# WAN emulator (Netropy 10G2) reference

Mapped 2026-10-11 on `http://192.168.173.213` (firmware 5.1.5) from three sources: a crawl of every
page, a field-by-field walk of every form (options switched in unsaved forms only), and the
box's own manuals (`/Netropy-Users-Guide.pdf` rev 5c and `/Netropy-API-Guide.pdf`, served by the
unit itself). The API guide describes the 4.0 REST routes. This box uses the YANG `/api` routes in
`wan_api.py`. UI helpers live in `pages/wan_emulator_page.py` (paths are described by
`pages/wan_path_spec.py`, and run against the NTG by `pages/wan_bench.py`).

## Model

| Concept | What it is | Where |
|---|---|---|
| **Engine** | An independent bridge between two ports, with its own paths, endpoints and stats. Engine 1 = emu ports 1/2, **Engine 2 = emu ports 3/4 = NTG Port 3 ⇄ Port 4**. | Engine tabs on Topology (`tab "Engine 2"`) |
| **Emulation** | On/off per engine. Off means a plain pass-through ("Bypass"). It is **off after every reboot**. | `checkbox "… Emulation"` (`label.emulation`) |
| **Path** | One set of conditions: an access link on each side plus the WAN in each direction. Up to 30 per engine. | left rail "Paths N" → `+` = `/path/create` |
| **Endpoint** | A classifier (port, VLAN, IP/range/subnet, TCP/UDP port; advanced: PCP, ToS, protocol, MAC, EtherType, MPLS, frame size, raw bytes) that sends matching traffic to a path. | "Endpoints N" → `/endpoint/create` |
| **Default Action** | Per port: where traffic matching no endpoint goes. **Bypass / Drop / \<path\>**. The suite points both ports at one path, so no endpoints are needed. | Topology header, `select[name=port-a|port-b]` |
| **Endpoint rules** | Pair endpoints on opposite ports to a path. | `/rules` |

The access link (bandwidth, queues) shapes rate. The WAN shapes delay, loss and errors. In
"single link" mode all traffic shares one link. "Per IP Source/Destination" gives each IP its own
link (only bandwidth, queue limit and frame overhead apply in that mode).

## Path form (`/path/create`, the same form for edits)

Every control has only a `name` attribute (no labels). Base fields, for each side
`source|destination`:

| Field `name` | Options (value=label) | Reveals |
|---|---|---|
| `label` | text, required | |
| `…/outbound/mode` | `single`, `per-ip-src`, `per-ip-dst` | |
| `…/outbound/bandwidth/rate` + `/metric` | number + `Gbps/Mbps/Kbps` (**default 128 Kbps**: open it up or NTG traffic crawls) | |
| `…/outbound/utilization/method` | `off`, `random` | `utilization/rate` (%), `utilization/burst` (64–2,000,000 B, default 1500) |
| `…/outbound/queue/algorithm` | `auto` (drop-tail sized to 250 ms of bandwidth), `drop-tail`, `random-early-detection` | `queue/depth`, `queue/unit` (`KB`/`packets`); RED adds `queue/minimum`, `queue/maximum` |
| `…/outbound/queue/strategy` | `fifo`, `priority`, `round-robin` | `queue/selector` (`ip` precedence / `vlan` PCP) |
| `…/outbound/mtu/enabled` | `false`, `true` | `mtu/limit` (68–9216), `mtu/send-icmp-error`, `mtu/fragmentation` (`standard`/`never`/`always`) |
| `…/outbound/frame/overhead` | `header-fcs` (18), `ethernet` (38), `custom` | `frame/size` (≤300) |
| `source/inbound/enabled`, `destination/inbound/enabled` | checkbox "ENABLED" (inbound access link) | |

**Which access link shapes which direction** (confirmed 2026-10-16 by a form round trip and the
stats layout): traffic source → destination enters through `source/outbound` and leaves through
`destination/inbound` (off unless its ENABLED box is ticked); destination → source uses
`destination/outbound` then `source/inbound`. So a cap on NTG Port 3 → 4 is
`source/outbound/bandwidth`, and its queue drops show in that direction's `inflow` stats.
The form lists the four links in chain order: source/outbound, destination/inbound,
source/inbound, destination/outbound.

Per direction, `wan/source-to-destination/…` and `wan/destination-to-source/…`:

| Impairment `…/method` | Options | Reveals (defaults) |
|---|---|---|
| `delay` | `off`, `constant`, `uniform`, `exponential`, `normal`, `burst` (Accumulate-Burst) | constant `latency` (ms, 0.01 steps); uniform `minimum`/`maximum`; exponential `minimum`/`mean`; normal `mean`/`standard-deviation` (mean ≥ 3σ); burst `count` (≤1000) / `delay` (ms, ≤10000) / `extra`. Variable kinds add `delay/reordering` ("Allow Reordering", off means delay is skewed to keep order) |
| `loss` | `off`, `random`, `burst`, `periodic`, `two-state` (Gilbert-Elliott), `bit-error-rate` | random `rate` % (`…/loss/random/rate`, a text input, default 0; saved as typed, checked 2026-10-16); burst `probability`/`minimum`/`maximum`; periodic `period`/`burst` (packets); G-E `good/rate`, `good/chance`, `bad/rate`, `bad/chance` (starts "good" each time emulation turns on); BER `coefficient` (1–<10) / `exponent` (≥ −18) |
| `outage` | `off`, `periodic` | `duration` (s), `interval` (s, start-to-start; duration > interval means a continuous outage); ranges like `1-5` allowed |
| `corruption` | `off`, `bit-error-rate` | `coefficient`/`exponent`. Never touches the Ethernet header or FCS |
| `reordering` | `off`, `on` | `probability` %, `offset` (packets, or a range `5-12`), `timeout` (ms, default 10000) |
| `duplication` | `off`, `on` | `probability` %. Duplicates get their own delay/loss/reorder |
| `mangle` | `off`, `ip` | `ip/selector` (`precedence`/`dscp`/`ecn`/`ds`/`custom`) + value. Checksums are recomputed, and max rate drops |

Revealed value fields sit under their block: `wan/<dir>/delay/normal/mean`, `…/delay/uniform/minimum`,
`…/outage/duration`, `…/reordering/probability`, `…/duplication/probability`, and so on.
`…/delay/reordering` ("Allow Reordering") is a checkbox, stored as a boolean. Every field T15–T21 use
round-trips through the real form (`tests/t0_library/test_t0_wan_library.py`, 2026-10-19).

Other controls on the form:
- A **presets** button (folder icon, no accessible name) right of the name box. Its menu groups open
  on **hover**; clicking a group closes the menu. Items (2026-10-19):

  | Group | Items |
  |---|---|
  | Cellular | 3G, 4G LTE, 5G, 5G Bad |
  | Wi-Fi | Good, Bad, 802.11a, 802.11b, 802.11g, 802.11n, 802.11ac |
  | Satellite | Good, Bad, LEO, MEO, GEO |
  | AWS | ap-northeast to us-west, ap-northeast to eu-west |
  | Cable | VDSL, T1, T3 |
  | SD-WAN | Good, Bad |

  Read back: **4G LTE** = 25 ms constant each way, caps 15 Mbps (a→b) / 12.5 Mbps (b→a), 0.01 %
  reordering. **GEO** = uniform 300–400 ms with Allow Reordering, caps 12 / 3 Mbps. **802.11n** =
  15 ms constant, 500 Mbps each way. All three keep the auto queue and 18-byte frame overhead.
- **Mirror** ↓/↑ copies one direction's settings to the other.
- **Playback** (`/path/create/playback`) drives bandwidth, latency or loss from a Recording file over
  time.
- **Create Path** saves the path; edits use **Apply Changes**. A path can't be deleted while it is a
  Default Action or used by an endpoint.

## Endpoint form (`/endpoint/create`)
`label`, `port` (1/2 on Engine 1, 3/4 on Engine 2), `vlans`, `ipaddrs`, `protocol` (`tcp`/`udp`),
`transports` (ports), `action` (`bypass`/`drop`/\<path\>; option values are path UUIDs, so select
by label). Submit is **Create Endpoint**; delete is behind the row's gear, like a path.
**An endpoint needs an address:** with only port and protocol, Create Endpoint silently saves
nothing: no error, the form just stays (2026-10-19, report). Stored as
`{"port": 3, "ipaddrs": "10.0.0.1", "protocol": "udp", "action": <path id>, ...}` under the engine's
`endpoint` list. **The protocol only classifies with a transport port range set**: with Transports empty, a UDP
endpoint also caught the TCP stream (2026-10-19), so T21 sets `1-65535`. T21 uses one endpoint per
(NTG port, stream protocol) with that port's IP; Default
Actions stay Bypass for everything else.

## Statistics
- **Topology**: click a path (or the `Bypass` entry) for a single-path graph (rate, frames, bytes;
  per direction or overlaid).
- **Detailed Statistics** (`/statistics`): rate, frames, bytes, drops, loss drops, reorders,
  duplicates, corruptions, plus access-link Tx rate/bytes/frames, queue length/drops and background
  traffic. The view spans 5 min–12 h. **Download View** opens a dialog: pick paths and statistics,
  interval or cumulative per-second counters, then `Download CSV` / `Cancel`. **Reset Totals**
  clears the counters for everyone, so the suite never clicks it; it diffs before/after instead.
- Counters reset on reboot and can't be recovered.
- API: `POST /api/apposite-netropy-device:get-stats-summary {"engine":2,"paths":[i]}` (totals) and
  `get-stats-records` (per second). The emulator **applies** latency but doesn't measure it. The
  NTG measures it.

## Administration (`/administration/...`)
| Page | Controls | Suite policy |
|---|---|---|
| mgmt/settings, mgmt/users | network settings, users; Apply/Cancel | read only |
| network/bridge-route, network/ethernet | bridge vs route mode, port speed/duplex; Apply/Cancel | read only (emu Port 4 is at 1G, which explains NTG Port 4 at 1G) |
| data/recordings | Add/Delete/Preview Recording, Apply | not used yet |
| engine/save | **Save Engine** downloads the engine config file | safe; useful to snapshot before a test |
| engine/restore | Browse / Restore Configuration / **Reset Configuration Engine N** | **never** |
| status/mgmt, status/log | management network status; **Engine Log** per engine (Previous/Next, rows/page, Mark Read, **Clear Log**) | read only, never Clear |
| upgrade/firmware, upgrade/license, upgrade/reboot | Upgrade, Apply Key, **Reboot** | **never** |

## Gotchas (from running T15)
- Default Action and Emulation changes **save asynchronously**. Change one control at a time and
  wait about 3 s before navigating, or the change is silently lost (`set_default_actions` handles
  this).
- Teardown order: Emulation off → Default Actions back to Bypass → delete the path.
- The GUI/API session is a 15-minute rolling cookie (`X-Apposite-Netropy`).
- `get-stats-records` with an unknown metric returns a bare 500.

## Seen 2026-10-19 (report)
- Create Endpoint without an IP address does nothing and says nothing (see the endpoint form).
- The preset button and the hover menu have no accessible names or roles.

## Seen 2026-10-11 (report)
- **Engine Log: "redundant power supply failure" (Oct 06 00:32:49)** on .213. That's hardware; tell
  whoever owns the box.
- Engine 2 state is clean: emulation off, 0 paths, 0 endpoints, Port 3/4 Default Action Bypass.
- Accessibility: no form control on the emulator has an accessible name (only `name=`), and icon
  buttons (`+`, presets, Mirror) have empty names.

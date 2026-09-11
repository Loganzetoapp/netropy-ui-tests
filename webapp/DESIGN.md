# Design System — Netropy Test Dashboard

Tokens extracted from two real Netropy Traffic Generator screenshots
(main dashboard, Create Testbed modal) and the Apposite Technologies
logo, provided 2026-09-10. This is a **theme match, not a screen clone**
— colors, type, and component styling come from here; this app's own
layout (tabs, test list, run flow, results table) is shaped around what
it actually needs, not copied from Netropy's specific screens.

## Color

| Token | Value | Use |
|---|---|---|
| `--bg` | `#EEF2F8` | Page background |
| `--surface` | `#FFFFFF` | Cards, modals, table rows |
| `--surface-2` | `#F5F7FB` | Subtle secondary surface (table header, hover, disabled panel) |
| `--border` | `#DCE3EE` | Card/table/input borders |
| `--ink` | `#16294A` | Primary text, headings, big numbers |
| `--ink-dim` | `#6B7686` | Secondary text, uppercase labels |
| `--accent` | `#1D4E8F` | Primary buttons, links, selected state |
| `--accent-hover` | `#16406F` | Primary button hover |
| `--ok` | `#1F8A4C` | "Available"/"Up"/passed |
| `--ok-bg` | `#E3F5E9` | Success pill background |
| `--warn` | `#8A6D1F` | "Reserved"-style pending/warning states |
| `--warn-bg` | `#FDF3D8` | Warning pill background |
| `--bad` | `#C23B3B` | "Down"/failed |
| `--bad-bg` | `#FBEAEA` | Failure pill/badge background |
| `--muted` | `#9AA3B0` | Disabled text/buttons |

Dark mode isn't part of this pass — Netropy's own UI has none, and this
is a short-session local utility, not something left open for hours.
Revisit only if asked for.

## Typography

- **Font:** Inter (Google Fonts), falling back to
  `-apple-system, "Segoe UI", Roboto, sans-serif`.
- **Scale:** 12px (uppercase labels, tracked +0.04em) / 14px (body,
  table cells) / 16px (section headings) / 28px (big stat numbers).
- Uppercase labels: `letter-spacing: 0.04em`, `color: var(--ink-dim)`,
  `font-weight: 600`.

## Buttons

- **Primary** ("Run", "Reserve"-style): `background: var(--accent)`,
  white text, `border-radius: 6px`, `padding: 6px 16px`,
  `font-weight: 600`; hover darkens to `--accent-hover`.
- **Disabled**: `background: transparent`, `color: var(--muted)`, same
  padding/radius, `cursor: not-allowed`.
- **Outline** (secondary actions, e.g. "Run all"): `background: transparent`,
  `border: 1px solid var(--border)`, `color: var(--ink)`.

## Status pills

Fully rounded (`border-radius: 999px`), `padding: 2px 10px`,
`font-size: 12px`, `font-weight: 600`:
- Positive (`passed`, "Safe"): `background: var(--ok-bg)`, `color: var(--ok)`.
- Warning/pending (`queued`, `running`, "Generates traffic"): `background: var(--warn-bg)`, `color: var(--warn)`.
- Negative (`failed`, `error`): `background: var(--bad-bg)`, `color: var(--bad)`.

## Cards

`background: var(--surface)`, `border: 1px solid var(--border)`,
`border-radius: 10px`, no heavy shadow — Netropy's own cards are flat
and bordered, not shadowed.

## Tables

Header row: `background: var(--surface-2)`, uppercase label style,
`border-bottom: 1px solid var(--border)`. Body rows:
`border-bottom: 1px solid var(--border)`, no zebra striping.

## Tiles (selectable/disabled cards)

`border: 1px solid var(--border)`, `border-radius: 8px`, `padding: 12px`;
selected: `border-color: var(--accent)`, `box-shadow: 0 0 0 1px var(--accent)`;
disabled ("coming soon"): `opacity: 0.5`, `cursor: not-allowed`.

## Modals

`background: var(--surface)`, `border-radius: 12px`,
`box-shadow: 0 10px 40px rgba(15,30,60,0.18)`, centered on a
semi-transparent dark scrim (`rgba(10,20,40,0.35)`).

## Tooltips

Dark: `background: #16294A`, white text, `border-radius: 6px`,
`padding: 4px 10px`, `font-size: 12px`.

## Logo

`webapp/static/apposite-logo.png` — header, left-aligned, ~28px tall,
next to the app name in `--ink`.

## Module tab icons

`webapp/static/icons/*.png` — one per module tab, icon-only (no baked-in
label; labels render in this app's own type, per Typography above), all
in the same two-tone style: `#27397A` navy linework, `#399E90` teal
accent, transparent background. 8 are cropped directly from real Netropy
product artwork; 5 (`rfc-9411`, `voip-sip`, `ott-video`, `threatstorm`,
`pqc` — no source artwork existed for these) were drawn to match, same
two colors sampled from the real ones. Displayed at a small, consistent
size (~28px tall) in the tab bar and larger (~64px) in the "coming soon"
empty state. Full mapping:

| Module | Icon file |
|---|---|
| Traffic Generator | `traffic-engine.png` |
| Session Strike | `session-strike.png` |
| RFC 2544 | `rfc-2544.png` |
| RFC 9411 | `rfc-9411.png` |
| AppPlayback | `app-playback.png` |
| AppStorm | `app-storm.png` |
| DDoS Storm | `ddos-storm.png` |
| DNS Storm | `dns-storm.png` |
| VoIP / SIP | `voip-sip.png` |
| OTT Video | `ott-video.png` |
| ThreatStorm | `threatstorm.png` |
| PQC | `pqc.png` |
| Attack Library | `attack-library.png` |

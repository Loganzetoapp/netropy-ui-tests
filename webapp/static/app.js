// selectedTests: nodeid -> safety_marker, so "Run selected" can compute a
// stateful-count warning without a second lookup against state.catalog.
// livePill: nodeid -> {text, cls, dot, done, runCode}, see setLiveStatus.
// testsView: what the Tests tab shows (area cards, one area, or matches).
const state = {
  catalog: null, liveStatus: {}, livePill: {}, batchRunning: false, selectedTests: new Map(),
  testsView: { area: null, query: "", filter: "all" },
  areaLabels: {}, // area id -> "T17 — WAN Bandwidth", for Back's label
};

// Dark mode toggle. The initial theme (if any was stored) is already
// applied by an inline <head> script before first paint — this just
// wires up flipping it from here on. Reads the OS preference directly
// rather than trusting any single CSS state, since "no stored choice"
// means the effective theme is whatever prefers-color-scheme says, and
// the toggle needs to know that to decide which way to flip.
function currentEffectiveTheme() {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit === "dark" || explicit === "light") return explicit;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const next = currentEffectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch (e) {
      // Private browsing / blocked storage — the toggle still works for
      // this page load, it just won't persist across a reload.
    }
  });
}
initThemeToggle();

// The logo and module icons are real product artwork with white
// backgrounds baked in, so each has a pre-generated dark variant
// (scripts/make_dark_icons.py). Emit both and let styles.css show the one
// matching the active theme — no JS needed when the theme flips.
function themedImg(src, alt = "") {
  const darkSrc = src.replace(/\/([^/]+)$/, "/dark/$1");
  return `<img src="${src}" alt="${alt}" class="img-light"><img src="${darkSrc}" alt="${alt}" class="img-dark">`;
}

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function loadModules() {
  const { modules } = await fetchJSON("/api/modules");
  const nav = document.getElementById("module-tabs");
  nav.hidden = false;
  nav.innerHTML = "";
  modules.forEach((m, i) => {
    const btn = document.createElement("button");
    btn.className = "tab" + (i === 0 ? " active" : "");
    btn.innerHTML = `${themedImg(m.icon)}<span>${m.name}</span>`;
    btn.addEventListener("click", () => selectModule(m, btn));
    nav.appendChild(btn);
  });
  selectModule(modules[0], nav.firstElementChild);
}

function selectModule(module, btn) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  btn.classList.add("active");
  const panel = document.getElementById("module-panel");
  if (!module.available) {
    panel.innerHTML = `
      <div class="coming-soon">
        ${themedImg(module.icon)}
        <h2>${module.name}</h2>
        <p>Test coverage for this module hasn't been built yet.</p>
      </div>`;
    return;
  }
  renderTrafficGenerator(panel);
}

// --- Tests tab: area cards -> one area's runnable list -----------------------
//
// Default view: one card per tests/ area (same grid as Overview), in
// T-number order, each test's last result shown as a dot. A card opens
// #tests/<area>, that area's runnable rows. Typing a search, or picking a
// filter other than "All", switches to a flat list of matches across every
// area, so finding a test never requires knowing its area.

const TEST_FILTERS = [
  { id: "all", label: "All", match: () => true },
  { id: "safe", label: "Safe", match: (t) => t.safety_marker !== "stateful" },
  { id: "traffic", label: "Generates traffic", match: (t) => t.safety_marker === "stateful" },
  { id: "wan", label: "WAN emulator", match: (t) => t.uses_wan },
  { id: "failing", label: "Failing", match: (t) => isFailing(t.last_result) },
  { id: "never", label: "Never run", match: (t) => !t.last_result },
];

function isFailing(last) {
  return !!last && (last.outcome === "fail" || last.outcome === "error");
}

// Every test in a group, each with its file (a row needs both).
function groupEntries(group) {
  return group.files.flatMap((file) => file.tests.map((test) => ({ test, file })));
}

function matchesQuery({ test, file }, group, q) {
  if (!q) return true;
  return [
    test.name, test.nodeid, test.description, test.full_description,
    file.short_description, file.full_description, group.label, group.description,
  ].join(" ").toLowerCase().includes(q);
}

async function renderTrafficGenerator(panel) {
  panel.innerHTML = "<p>Loading tests…</p>";
  // A fresh catalog render always starts from a clean slate — checkboxes
  // below are unchecked by construction, so any nodeids left in the map
  // from a previous render (e.g. the user navigated away mid-selection)
  // would otherwise silently disagree with what's on screen.
  state.selectedTests.clear();
  try {
    const { groups } = await fetchJSON("/api/catalog");
    state.catalog = groups;
    groups.forEach((g) => { state.areaLabels[g.id] = g.label; });
    updateBackButton();
    panel.innerHTML = `
      <div class="filter-field">
        <input type="search" id="tests-filter" class="filter-input" placeholder="Search all tests…"
          aria-label="Search all tests" value="${escapeAttr(state.testsView.query)}">
      </div>
      <div class="filter-chips" role="group" aria-label="Show only">
        ${TEST_FILTERS.map(renderFilterChip).join("")}
      </div>
      <div id="selection-bar" class="selection-bar" hidden>
        <span id="selection-count"></span>
        <div class="selection-bar-actions">
          <button type="button" class="btn-outline" id="selection-clear">Clear</button>
          <button type="button" class="btn-primary" id="selection-run">Run selected</button>
        </div>
      </div>
      <div id="tests-body"></div>`;
    attachTestsToolbar();
    renderTestsBody();
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load tests: ${escapeHtml(err.message)}</p>`;
  }
}

function renderFilterChip(filter) {
  const count = state.catalog.flatMap(groupEntries).filter(({ test }) => filter.match(test)).length;
  const active = state.testsView.filter === filter.id;
  return `<button type="button" class="chip${active ? " active" : ""}" aria-pressed="${active}"
    data-filter="${filter.id}">${filter.label} <span class="chip-count">${count}</span></button>`;
}

// Toolbar controls live outside #tests-body, so they're wired once per
// Tests-tab render; the body re-renders on every search keystroke.
function attachTestsToolbar() {
  const input = document.getElementById("tests-filter");
  input.addEventListener("input", () => {
    state.testsView.query = input.value;
    renderTestsBody();
  });
  document.querySelectorAll(".filter-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.testsView.filter = chip.dataset.filter;
      syncTestsToolbar();
      renderTestsBody();
    });
  });
  document.getElementById("selection-clear").addEventListener("click", clearTestSelection);
  document.getElementById("selection-run").addEventListener("click", () => {
    const nodeids = Array.from(state.selectedTests.keys());
    const statefulCount = Array.from(state.selectedTests.values()).filter(
      (marker) => marker === "stateful"
    ).length;
    openRunSelectedModal(nodeids, statefulCount, document.getElementById("selection-run"));
  });
}

function syncTestsToolbar() {
  const input = document.getElementById("tests-filter");
  if (input && input.value !== state.testsView.query) input.value = state.testsView.query;
  document.querySelectorAll(".filter-chips .chip").forEach((chip) => {
    const on = chip.dataset.filter === state.testsView.filter;
    chip.classList.toggle("active", on);
    chip.setAttribute("aria-pressed", String(on));
  });
}

function renderTestsBody() {
  const body = document.getElementById("tests-body");
  if (!body || !state.catalog) return;
  const { query, filter, area } = state.testsView;
  const q = query.trim().toLowerCase();
  const match = (TEST_FILTERS.find((f) => f.id === filter) || TEST_FILTERS[0]).match;
  if (q || filter !== "all") {
    const sections = state.catalog
      .map((group) => ({
        group,
        entries: groupEntries(group).filter((e) => match(e.test) && matchesQuery(e, group, q)),
      }))
      .filter((s) => s.entries.length);
    const total = sections.reduce((n, s) => n + s.entries.length, 0);
    body.innerHTML = total
      ? `<p class="tests-result-count">${total} test${total === 1 ? "" : "s"} match</p>
         ${sections.map((s) => renderGroup(s.group, s.entries, true)).join("")}`
      : `<p class="test-desc">No tests match.</p>`;
  } else if (area) {
    const group = state.catalog.find((g) => g.id === area);
    body.innerHTML = group
      ? renderAreaTests(group)
      : `<div class="breadcrumb-row"><a href="#tests">← All areas</a></div>
         <p class="test-desc">No test area "${escapeHtml(area)}".</p>`;
  } else {
    body.innerHTML = `<div class="overview-grid">${state.catalog.map(renderTestAreaCard).join("")}</div>`;
  }
  attachTestsBodyHandlers(body);
  Object.keys(state.livePill).forEach(applyLiveStatus);
}

// --- Area cards ------------------------------------------------------------

const DOT_CLASS = { pass: "dot-pass", fail: "dot-fail", error: "dot-fail", skip: "dot-skip" };

function renderResultDot(test) {
  const last = test.last_result;
  const cls = last ? DOT_CLASS[last.outcome] || "dot-skip" : "dot-never";
  const what = last
    ? `${last.outcome}${last.cases > 1 ? `, ${last.passed}/${last.cases} cases passed` : ""} (${last.run_code || "unlinked run"})`
    : "never run";
  return `<span class="result-dot ${cls}" data-dot-for="${escapeAttr(test.nodeid)}"
    title="${escapeAttr(`${test.name}: ${what}`)}"></span>`;
}

// Same card shape as Overview's, but its job is "what's in here and can I
// run it": counts, hardware needs, last results. The title is a real link
// (keyboard/AT reach it like any link); a click anywhere else on the card
// that isn't the Run all button does the same.
function renderTestAreaCard(group) {
  const tests = groupEntries(group).map((e) => e.test);
  const safe = tests.filter((t) => t.safety_marker !== "stateful").length;
  const traffic = tests.length - safe;
  const cases = tests.reduce((n, t) => n + (t.param_count || 1), 0);
  const passing = tests.filter((t) => t.last_result && t.last_result.outcome === "pass").length;
  const failing = tests.filter((t) => isFailing(t.last_result)).length;
  const never = tests.filter((t) => !t.last_result).length;
  const skipped = tests.length - passing - failing - never;
  const summary = [
    passing && `${passing} passing`,
    failing && `${failing} failing`,
    skipped && `${skipped} skipped`,
    never && `${never} never run`,
  ].filter(Boolean).join(" · ");
  const groupName = group.label.split(" — ")[0];
  return `
    <div class="card area-card test-area-card" data-area-id="${escapeAttr(group.id)}">
      <div class="area-card-header">
        <h3><a class="area-card-link" href="#tests/${encodeURIComponent(group.id)}">${escapeHtml(group.label)}</a></h3>
        <span class="area-card-count">${tests.length} test${tests.length === 1 ? "" : "s"}${
          cases > tests.length ? ` · ${cases} cases` : ""}</span>
      </div>
      ${group.description ? `<p class="area-card-desc">${escapeHtml(group.description)}</p>` : ""}
      <div class="area-card-row">
        ${safe ? `<span class="pill pill-ok">${safe} safe</span>` : ""}
        ${traffic ? `<span class="pill pill-warn">${traffic} traffic</span>` : ""}
        ${tests.some((t) => t.uses_wan) ? `<span class="pill pill-wan">WAN emulator</span>` : ""}
      </div>
      <div class="result-dots" aria-hidden="true">${tests.map(renderResultDot).join("")}</div>
      <div class="area-card-foot">
        <span class="test-desc">${summary}</span>
        ${runAllButton(tests.map((t) => t.nodeid), traffic, groupName, "Run all")}
      </div>
    </div>`;
}

// --- One area / search results -------------------------------------------

function renderAreaTests(group) {
  return `
    <div class="breadcrumb-row breadcrumb-split">
      <a href="#tests">← All areas</a>
      <a href="#area/${encodeURIComponent(group.id)}">History &amp; known issues →</a>
    </div>
    ${group.description ? `<p class="area-intro">${escapeHtml(group.description)}</p>` : ""}
    ${renderGroup(group, groupEntries(group), false)}`;
}

// `entries` may be a subset (search results), and Run all runs exactly
// what's listed, so it's labelled that way rather than "Run all in T5".
function renderGroup(group, entries, linkTitle) {
  const nodeids = entries.map((e) => e.test.nodeid);
  const statefulCount = entries.filter((e) => e.test.safety_marker === "stateful").length;
  const groupName = group.label.split(" — ")[0];
  const subset = entries.length < groupEntries(group).length;
  const title = linkTitle
    ? `<a href="#tests/${encodeURIComponent(group.id)}">${escapeHtml(group.label)}</a>`
    : escapeHtml(group.label);
  return `
    <section class="group" data-group-id="${escapeAttr(group.id)}">
      <div class="group-header">
        <h2>${title}</h2>
        ${subset
          ? runAllButton(nodeids, statefulCount, `${groupName} (${entries.length} shown)`, `Run these ${entries.length}`)
          : runAllButton(nodeids, statefulCount, groupName, `Run all in ${groupName}`)}
      </div>
      ${entries.map((e) => renderTestRow(e.test, e.file)).join("")}
    </section>`;
}

function runAllButton(nodeids, statefulCount, groupName, label) {
  return `<button type="button" class="btn-outline run-all-btn"
    data-nodeids="${escapeAttr(JSON.stringify(nodeids))}"
    data-stateful-count="${statefulCount}"
    data-group-name="${escapeAttr(groupName)}">${escapeHtml(label)}</button>`;
}

function safetyPill(marker) {
  if (marker === "stateful") return `<span class="pill pill-warn">Generates traffic</span>`;
  return `<span class="pill pill-ok">Safe</span>`;
}

function renderLastResult(last) {
  if (!last) return `<span class="last-result muted-cell">never run</span>`;
  const cases = last.cases > 1 ? `<span class="muted-cell">${last.passed}/${last.cases}</span>` : "";
  const code = last.run_code
    ? `<a href="#run/${encodeURIComponent(last.run_code)}">${escapeHtml(last.run_code)}</a>`
    : "";
  return `<span class="last-result">${outcomePill(last.outcome, last.failure_kind)}${cases}${code}</span>`;
}

function renderTestRow(test, file) {
  // A test's own docstring says what it checks; tests without one fall
  // back to their file's (several tests can share a file).
  const desc = test.description || file.short_description;
  const fullDesc = [test.full_description, file.full_description].filter(Boolean).join("\n\n");
  const cases = test.param_count
    ? `<span class="pill pill-muted">${test.param_count} cases</span>`
    : test.param_count === 0 ? `<span class="pill pill-muted">parametrized</span>` : "";
  const checked = state.selectedTests.has(test.nodeid) ? " checked" : "";
  return `
    <div class="test-row" data-nodeid="${escapeAttr(test.nodeid)}" data-full-description="${escapeAttr(fullDesc)}">
      <div class="test-row-main">
        <input type="checkbox" class="test-select" data-nodeid="${escapeAttr(test.nodeid)}"
          data-marker="${test.safety_marker}" aria-label="Select ${escapeAttr(test.name)}"${checked}>
        <div class="test-row-text">
          <div class="test-name">${escapeHtml(test.name)}</div>
          <div class="test-desc">${escapeHtml(desc)}</div>
        </div>
      </div>
      <div class="test-row-actions">
        ${renderLastResult(test.last_result)}
        <span class="pill" data-status-for="${escapeAttr(test.nodeid)}"></span>
        ${cases}
        ${test.uses_wan ? `<span class="pill pill-wan">WAN</span>` : ""}
        ${safetyPill(test.safety_marker)}
        <button type="button" class="btn-primary run-btn" data-nodeid="${escapeAttr(test.nodeid)}"
          data-marker="${test.safety_marker}">Run</button>
      </div>
    </div>`;
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

// History (and therefore the run-detail page) records the nodeid
// pytest-playwright actually produced, e.g. "...::test_x[chromium]" — but
// POST /api/runs, and the whole Tests-tab catalog it validates against,
// only ever knows the bare, no-suffix nodeid built from source (see
// app.py's _marker_for and runner.py's _matches_catalog_nodeid, which
// document this exact split). Strip the suffix before handing a
// history-sourced nodeid back to startRun/openRunModal, or "Run again"
// 404s against a nodeid the catalog was never going to recognize.
function catalogNodeid(nodeid) {
  const idx = nodeid.lastIndexOf("[");
  return idx === -1 ? nodeid : nodeid.slice(0, idx);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function attachTestsBodyHandlers(body) {
  body.querySelectorAll(".test-area-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest("a, button")) return; // the title link and Run all handle themselves
      location.hash = `tests/${encodeURIComponent(card.dataset.areaId)}`;
    });
  });
  body.querySelectorAll(".test-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest(".run-btn, .test-select, a")) return;
      toggleDetail(row);
    });
  });
  body.querySelectorAll(".run-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openRunModal(btn.dataset.nodeid, btn.dataset.marker, btn);
    });
  });
  body.querySelectorAll(".run-all-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const nodeids = JSON.parse(btn.dataset.nodeids);
      const statefulCount = parseInt(btn.dataset.statefulCount, 10) || 0;
      if (statefulCount > 0) {
        // At least one stateful test in this set — same hazard as the
        // single-test Run modal's warning, just naming the group instead
        // of one nodeid. Block on confirmation before anything runs.
        openRunAllModal(nodeids, btn.dataset.groupName, statefulCount, btn);
      } else {
        // All hardware_free — no traffic risk, no added friction.
        runAllInGroup(nodeids);
      }
    });
  });
  body.querySelectorAll(".test-select").forEach((cb) => {
    cb.addEventListener("change", () => {
      const nodeid = cb.dataset.nodeid;
      if (cb.checked) state.selectedTests.set(nodeid, cb.dataset.marker);
      else state.selectedTests.delete(nodeid);
      updateSelectionBar();
    });
  });
  // A batch may already be running (e.g. the user switched tabs and back
  // mid-run) — newly attached buttons need to reflect that immediately.
  setRunControlsEnabled(!state.batchRunning);
}

// Reflects state.selectedTests onto the selection bar (count text,
// visibility) — called on every checkbox change so the bar never lags
// behind what's actually checked.
function updateSelectionBar() {
  const bar = document.getElementById("selection-bar");
  if (!bar) return;
  const count = state.selectedTests.size;
  bar.hidden = count === 0;
  document.getElementById("selection-count").textContent =
    `${count} test${count === 1 ? "" : "s"} selected`;
}

// Selection is a one-shot batch of independent single-test runs, same
// mental model as "Run all in group" — once confirmed, it's spent; the
// bar goes away and the next selection starts clean.
function clearTestSelection() {
  state.selectedTests.clear();
  document.querySelectorAll(".test-select").forEach((cb) => (cb.checked = false));
  updateSelectionBar();
}

function toggleDetail(row) {
  const existing = row.nextElementSibling;
  if (existing && existing.classList.contains("detail-panel")) {
    existing.remove();
    return;
  }
  document.querySelectorAll(".detail-panel").forEach((p) => p.remove());
  const panel = document.createElement("div");
  panel.className = "detail-panel";
  panel.textContent = row.dataset.fullDescription;
  row.after(panel);
}

// --- Live run status ---------------------------------------------------------
//
// Kept per test in state, not only in whichever row was on screen when the
// run started, so it survives moving between the cards, an area and a
// search, and shows on both the row pill and the card dot.

function setLiveStatus(nodeid, patch) {
  state.livePill[nodeid] = { ...(state.livePill[nodeid] || {}), ...patch };
  applyLiveStatus(nodeid);
}

function applyLiveStatus(nodeid) {
  const live = state.livePill[nodeid];
  if (!live) return;
  const sel = CSS.escape(nodeid);
  document.querySelectorAll(`[data-status-for="${sel}"]`).forEach((el) => {
    el.textContent = live.text;
    el.className = `pill ${live.cls}`;
    // The "View summary →" link sits next to the pill once the batch is
    // done; a re-run must not leave the previous run's link up.
    const actions = el.closest(".test-row-actions");
    if (!actions) return;
    const stale = actions.querySelector(".view-summary-link");
    if (stale) stale.remove();
    if (live.done && live.runCode) {
      const link = document.createElement("a");
      link.href = `#run/${encodeURIComponent(live.runCode)}`;
      link.className = "view-summary-link";
      link.textContent = "View summary →";
      actions.appendChild(link);
    }
  });
  document.querySelectorAll(`[data-dot-for="${sel}"]`).forEach((dot) => {
    dot.className = `result-dot ${live.dot}`;
  });
}

function dotForStatus(status) {
  if (status === "passed") return "dot-pass";
  if (status === "failed" || status === "error") return "dot-fail";
  if (status === "running") return "dot-running";
  return "dot-skip";
}

// modalMode distinguishes the three things this one modal now confirms:
// "single" (openRunModal — repeat-count field, calls startRun), "group"
// (openRunAllModal — no repeat count, every test runs once, calls
// runAllInGroup), and "selected" (openRunSelectedModal — repeat count
// applies to EACH selected test, calls runSelectedTests).
// Which box a run points at. Presets come from /api/targets (see
// webapp/targets.py); "Custom…" takes any IP/URL. The choice is remembered
// per browser so it sticks across runs, and is validated again server-side.
const TARGET_STORAGE_KEY = "netropy-dash-target";
const TARGET_CUSTOM_STORAGE_KEY = "netropy-dash-target-custom";
const CUSTOM_TARGET = "__custom__";
let targetsInfo = null;
// Set when the run modal is confirmed; read by startRun for every run in
// that batch (single, selected, or run-all).
let runTarget = null;

function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeStored(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode etc. */ }
}

async function populateTargetSelect() {
  const select = document.getElementById("run-modal-target");
  if (!targetsInfo) {
    try {
      targetsInfo = await fetchJSON("/api/targets");
    } catch {
      targetsInfo = { default: "", presets: [] };
    }
  }
  select.innerHTML = "";
  for (const preset of targetsInfo.presets) {
    const opt = document.createElement("option");
    opt.value = preset.url;
    opt.textContent = `${preset.label} — ${preset.url.replace(/^https?:\/\//, "")}`;
    select.appendChild(opt);
  }
  const custom = document.createElement("option");
  custom.value = CUSTOM_TARGET;
  custom.textContent = "Custom…";
  select.appendChild(custom);

  const stored = readStored(TARGET_STORAGE_KEY);
  const known = [...select.options].some((o) => o.value === stored);
  select.value = known ? stored : targetsInfo.default || select.options[0].value;
  document.getElementById("run-modal-target-custom").value =
    readStored(TARGET_CUSTOM_STORAGE_KEY) || "";
  syncCustomTargetField();
}

function syncCustomTargetField() {
  const isCustom = document.getElementById("run-modal-target").value === CUSTOM_TARGET;
  document.getElementById("run-modal-target-custom-field").hidden = !isCustom;
  document.getElementById("run-modal-target-error").hidden = true;
}

// Returns the chosen target URL, or null after showing an inline error.
// Loose client-side shape check only; the server does the real validation.
function selectedTargetOrError() {
  const errorEl = document.getElementById("run-modal-target-error");
  const value = document.getElementById("run-modal-target").value;
  if (value !== CUSTOM_TARGET) {
    writeStored(TARGET_STORAGE_KEY, value);
    return value;
  }
  const raw = document.getElementById("run-modal-target-custom").value.trim();
  if (!/^(https?:\/\/)?[A-Za-z0-9.\-]+(:\d{1,5})?\/?$/.test(raw)) {
    errorEl.textContent = raw
      ? "That doesn't look like an IP address or URL (e.g. 192.168.173.120 or http://10.0.0.5:8080)."
      : "Enter an IP address or URL for the custom target.";
    errorEl.hidden = false;
    document.getElementById("run-modal-target-custom").focus();
    return null;
  }
  writeStored(TARGET_STORAGE_KEY, CUSTOM_TARGET);
  writeStored(TARGET_CUSTOM_STORAGE_KEY, raw);
  return raw;
}

document.getElementById("run-modal-target").addEventListener("change", () => {
  syncCustomTargetField();
  if (document.getElementById("run-modal-target").value === CUSTOM_TARGET) {
    document.getElementById("run-modal-target-custom").focus();
  }
});
document.getElementById("run-modal-target-custom").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    document.getElementById("run-modal-confirm").click();
  }
});

let modalMode = null;
let modalNodeid = null;
let modalGroupNodeids = null;
let modalTriggerEl = null;

function openRunModal(nodeid, marker, triggerEl) {
  modalMode = "single";
  modalNodeid = nodeid;
  modalTriggerEl = triggerEl || document.activeElement;
  document.getElementById("run-modal-title").textContent = "Run test";
  const warning = document.getElementById("run-modal-warning");
  warning.textContent = "⚠ This generates real network traffic on the lab hardware.";
  warning.hidden = marker !== "stateful";
  document.getElementById("run-modal-count-field").hidden = false;
  document.getElementById("run-modal-count-label").textContent = "How many times?";
  document.getElementById("run-modal-confirm").textContent = "Run";
  const countInput = document.getElementById("run-modal-count");
  countInput.value = 1;
  document.getElementById("run-modal-headed").checked = false;
  populateTargetSelect();
  document.getElementById("run-modal").hidden = false;
  // Land keyboard focus in the field people are most likely to change,
  // with its default value pre-selected so typing overwrites it.
  countInput.focus();
  countInput.select();
}

// Same modal as openRunModal, but for a cross-group set of individually
// checked tests rather than one nodeid — the repeat-count field stays
// visible (unlike "group" mode) since it's the whole point here: "how
// many times should each selected test run", not a single shared count
// for one test.
function openRunSelectedModal(nodeids, statefulCount, triggerEl) {
  modalMode = "selected";
  modalGroupNodeids = nodeids;
  modalTriggerEl = triggerEl || document.activeElement;
  document.getElementById("run-modal-title").textContent =
    `Run ${nodeids.length} selected test${nodeids.length === 1 ? "" : "s"}`;
  const warning = document.getElementById("run-modal-warning");
  if (statefulCount > 0) {
    warning.textContent =
      `⚠ Run ${nodeids.length} selected tests? ${statefulCount} of these generate ` +
      `real network traffic on the lab hardware.`;
    warning.hidden = false;
  } else {
    warning.hidden = true;
  }
  document.getElementById("run-modal-count-field").hidden = false;
  document.getElementById("run-modal-count-label").textContent = "How many times should each test run?";
  document.getElementById("run-modal-confirm").textContent = "Run";
  const countInput = document.getElementById("run-modal-count");
  countInput.value = 1;
  document.getElementById("run-modal-headed").checked = false;
  populateTargetSelect();
  document.getElementById("run-modal").hidden = false;
  countInput.focus();
  countInput.select();
}

// Confirmation gate for "Run all in T<N>" when the group contains any
// stateful test — the group-level equivalent of openRunModal's warning.
// Per the plan, run-all never prompts for a repeat count (that's a
// single-test-only concept), so the count field stays hidden here.
function openRunAllModal(nodeids, groupName, statefulCount, triggerEl) {
  modalMode = "group";
  modalGroupNodeids = nodeids;
  modalTriggerEl = triggerEl || document.activeElement;
  document.getElementById("run-modal-title").textContent = `Run all in ${groupName}`;
  const warning = document.getElementById("run-modal-warning");
  warning.textContent =
    `⚠ Run all ${nodeids.length} tests in ${groupName}? ${statefulCount} of these generate ` +
    `real network traffic on the lab hardware.`;
  warning.hidden = false;
  document.getElementById("run-modal-count-field").hidden = true;
  document.getElementById("run-modal-confirm").textContent = "Run all";
  document.getElementById("run-modal-headed").checked = false;
  populateTargetSelect();
  document.getElementById("run-modal").hidden = false;
  document.getElementById("run-modal-confirm").focus();
}

function closeRunModal() {
  document.getElementById("run-modal").hidden = true;
  if (modalTriggerEl) modalTriggerEl.focus();
}

document.getElementById("run-modal-close").addEventListener("click", closeRunModal);

// Clicking the dimmed backdrop (not the modal card itself) closes it, and
// so does Escape — standard modal conventions the brief's markup already
// supports but didn't wire up.
document.getElementById("run-modal").addEventListener("click", (e) => {
  if (e.target.id === "run-modal") closeRunModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !document.getElementById("run-modal").hidden) closeRunModal();
});
document.getElementById("run-modal-count").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    document.getElementById("run-modal-confirm").click();
  }
});

document.getElementById("run-modal-confirm").addEventListener("click", async () => {
  const headed = document.getElementById("run-modal-headed").checked;
  const target = selectedTargetOrError();
  if (target === null) return;
  runTarget = target;
  // The modal can now be opened from pages other than Tests (e.g. the
  // run-detail page's "Run again" button) — the live status pill
  // streamRun updates only exists on a Tests-tab row, so jump there first
  // so progress is actually visible. Skipped when already on Tests (the
  // normal case) so an in-progress expanded description panel etc. isn't
  // disturbed by a needless re-render.
  const alreadyOnTests = document.getElementById("nav-tests").classList.contains("active");
  if (modalMode === "group") {
    const nodeids = modalGroupNodeids;
    closeRunModal();
    // Must finish rendering the real Tests-tab rows before starting the
    // run — streamRun looks up its status pill by nodeid immediately
    // after the run starts, and that element doesn't exist until this
    // resolves. Racing the two would silently drop the live status/View
    // summary link the first time (loadModules replaces panel.innerHTML
    // out from under whatever streamRun already found).
    if (!alreadyOnTests) await showPage("tests");
    await runAllInGroup(nodeids, headed);
    return;
  }
  if (modalMode === "selected") {
    const nodeids = modalGroupNodeids;
    const raw = parseInt(document.getElementById("run-modal-count").value, 10);
    const count = Number.isFinite(raw) && raw > 0 ? raw : 1;
    closeRunModal();
    // Same rendering-order reasoning as "group" above — plus this clears
    // the just-used selection, so it must happen on the real Tests-tab
    // render (a fresh renderTrafficGenerator call also clears
    // state.selectedTests itself; calling clearTestSelection() here too
    // covers the alreadyOnTests case, where that fresh render never runs).
    if (!alreadyOnTests) await showPage("tests");
    clearTestSelection();
    await runSelectedTests(nodeids, count, headed);
    return;
  }
  const raw = parseInt(document.getElementById("run-modal-count").value, 10);
  const count = Number.isFinite(raw) && raw > 0 ? raw : 1;
  const nodeid = modalNodeid;
  closeRunModal();
  if (!alreadyOnTests) {
    // e.g. "Run again" on a run page: land on the test's own area so its
    // row (live pill, "View summary") is on screen. replaceState, not a
    // hash assignment: a hashchange would re-render under the run below.
    const area = nodeid.split("/")[1] || null;
    state.testsView = { area, query: "", filter: "all" };
    history.replaceState(null, "", area ? `#tests/${encodeURIComponent(area)}` : "#tests");
    navStack[navStack.length - 1] = location.hash;
    updateBackButton();
    await showPage("tests");
  }
  await startRun(nodeid, count, headed);
});

// Returns true once the batch is confirmed started (streamRun has taken
// over), false if the request was rejected (e.g. a 409 from another
// batch already running) — callers that chain multiple runs (see
// runAllInGroup) need this to know not to wait on a run that never
// started.
async function startRun(nodeid, repeatCount, headed = false) {
  try {
    const { batch_id } = await fetchJSON("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nodeid, repeat_count: repeatCount, headed, target_url: runTarget }),
    });
    streamRun(batch_id, nodeid);
    return true;
  } catch (err) {
    alert(err.message);
    return false;
  }
}

function statusPillClass(status) {
  if (status === "passed") return "pill-ok";
  if (status === "failed" || status === "error") return "pill-bad";
  return "pill-warn";
}

// The backend allows exactly one batch to run at a time, globally
// (webapp/runner.py) — mirroring that here means a queued-up second
// click never has to round-trip to a 409 just to find out it can't run.
function setRunControlsEnabled(enabled) {
  document.querySelectorAll(".run-btn, .run-all-btn").forEach((btn) => {
    btn.disabled = !enabled;
  });
}

function streamRun(batchId, nodeid) {
  let lastRunCode = null;
  state.liveStatus[nodeid] = "running";
  state.batchRunning = true;
  setRunControlsEnabled(false);
  // Reflect "running" the instant the batch is confirmed started, rather
  // than waiting on the first SSE round-trip (pytest collection can take
  // a beat before the first iteration event arrives). Clearing runCode
  // also takes down a previous run's "View summary" link.
  setLiveStatus(nodeid, { text: "running", cls: "pill-warn", dot: "dot-running", done: false, runCode: null });
  const source = new EventSource(`/api/runs/${batchId}/stream`);
  const finish = () => {
    state.batchRunning = false;
    setRunControlsEnabled(true);
  };
  source.onmessage = (e) => {
    const payload = JSON.parse(e.data);
    if (payload.type === "iteration") {
      if (payload.run_code) lastRunCode = payload.run_code;
      setLiveStatus(nodeid, {
        text: `${payload.status} (${payload.iteration}/${payload.total})`,
        cls: statusPillClass(payload.status),
        dot: dotForStatus(payload.status),
      });
    } else if (payload.type === "batch_complete") {
      state.liveStatus[nodeid] = "done";
      // lastRunCode is the most recent iteration's code — for the common
      // repeat_count=1 case that's the only run; for a repeat run it's
      // the last one, which is what "View summary" should point at.
      setLiveStatus(nodeid, { text: `${payload.passed}/${payload.total} passed`, done: true, runCode: lastRunCode });
      source.close();
      finish();
    }
  };
  source.onerror = () => {
    source.close();
    state.liveStatus[nodeid] = "done";
    finish();
  };
}

// Shared by runAllInGroup (repeatCount always 1) and runSelectedTests
// (repeatCount is whatever the "Run selected" modal's count field says) —
// both are "start each nodeid, wait for it to finish, then start the
// next" with identical failure handling; only the count differs.
async function runNodeidsSequentially(nodeids, repeatCount, headed, actionLabel) {
  for (const nodeid of nodeids) {
    const started = await startRun(nodeid, repeatCount, headed);
    if (!started) {
      // startRun already alerted with the specific reason (e.g. a 409
      // from another batch running). Without this, the loop would go on
      // to await a state.liveStatus[nodeid] === "done" that streamRun
      // never got the chance to set, polling forever on a leaked
      // interval. Stop the sequence here instead of hanging silently.
      alert(`${actionLabel} stopped before finishing — "${nodeid}" could not be started.`);
      return;
    }
    await new Promise((resolve) => {
      const check = setInterval(() => {
        if (state.liveStatus[nodeid] === "done") {
          clearInterval(check);
          resolve();
        }
      }, 300);
    });
  }
}

async function runAllInGroup(nodeids, headed = false) {
  return runNodeidsSequentially(nodeids, 1, headed, "Run all");
}

async function runSelectedTests(nodeids, repeatCount, headed = false) {
  return runNodeidsSequentially(nodeids, repeatCount, headed, "Run selected");
}

// Tests, like Overview, is hash-addressable (#tests, #tests/<area>) so an
// area can be linked to and Back works between cards and an area.
function goToTests() {
  if (location.hash === "#tests") {
    openTestsView(null);
  } else {
    location.hash = "tests";
  }
}
document.getElementById("nav-tests").addEventListener("click", goToTests);
// Results and Findings are hash routes too, so every page is a browser
// history entry and Back (the button, or the browser's) steps through them.
function goToPage(name) {
  if (location.hash === `#${name}`) {
    showPage(name);
  } else {
    location.hash = name;
  }
}
document.getElementById("nav-results").addEventListener("click", () => goToPage("results"));
document.getElementById("nav-findings").addEventListener("click", () => goToPage("findings"));
// Overview is the one page-nav tab that's also address-bar-linkable (see
// the routing block near the bottom of this file). Setting the hash (when
// it actually changes) lets the hashchange listener drive the render, so
// clicking here behaves identically to landing directly on #overview;
// when the hash is already "#overview" (no change → no hashchange event
// would fire) render directly instead.
function goToOverview() {
  if (location.hash === "#overview") {
    showPage("overview");
  } else {
    location.hash = "overview";
  }
}
document.getElementById("nav-overview").addEventListener("click", goToOverview);
document.getElementById("logo-home").addEventListener("click", goToOverview);

// Returns the underlying render call's promise (all four are async
// functions) so a caller that needs the panel to actually be populated
// before doing anything else — see the run-modal confirm handler's
// "switch to Tests tab first" case — can `await showPage(...)`. Existing
// callers (the plain nav-button clicks) don't await it, which is fine —
// this is purely additive, nothing about the fire-and-forget behavior
// they already relied on changes.
function showPage(page) {
  document.getElementById("nav-overview").classList.toggle("active", page === "overview");
  document.getElementById("nav-tests").classList.toggle("active", page === "tests");
  document.getElementById("nav-results").classList.toggle("active", page === "results");
  document.getElementById("nav-findings").classList.toggle("active", page === "findings");
  const tabs = document.getElementById("module-tabs");
  const panel = document.getElementById("module-panel");
  if (page === "overview") {
    tabs.hidden = true;
    return renderOverview(panel);
  } else if (page === "results") {
    tabs.hidden = true;
    return renderResults(panel);
  } else if (page === "findings") {
    tabs.hidden = true;
    return renderFindings(panel);
  } else {
    tabs.hidden = false;
    return loadModules();
  }
}

// --- Overview tab (per-catalog-area rollup) ---------------------------------

function outcomePillClass(outcome) {
  // Covers both vocabularies this app uses: history/API outcomes
  // ("pass"/"fail"/"error"/"skip") and SSE iteration statuses
  // ("passed"/"failed"/"error"/"running").
  if (outcome === "pass" || outcome === "passed") return "pill-ok";
  if (outcome === "fail" || outcome === "failed" || outcome === "error") return "pill-bad";
  // A skip didn't run (e.g. the bench was busy): neutral, not a warning.
  if (outcome === "skip" || outcome === "skipped") return "pill-muted";
  return "pill-warn";
}

// A failure the suite attributed to the unit itself being unhealthy
// (offline / recovery mode / disconnected testbed / lost run stats) —
// conftest.py's SystemBadStateError, recorded as failure_kind "system".
// Shown as its own pill so it isn't mistaken for a test finding a bug in
// a healthy unit.
function outcomePill(outcome, failureKind) {
  if (failureKind === "system" && (outcome === "fail" || outcome === "error")) {
    return `<span class="pill pill-system" data-tip="The unit itself was unhealthy (offline, recovery mode, or run results lost)">system failure</span>`;
  }
  return `<span class="pill ${outcomePillClass(outcome)}">${escapeHtml(outcome)}</span>`;
}

// --- Known-issue status (open/investigating/fixed) ----------------------------
//
// Status comes from webapp/known_issues.py's classify_status() — a
// lightweight keyword read of the findings doc's free-text "Status: ..."
// line, never a certainty. Colors follow the same semantics as
// outcomePillClass: open (unresolved) reads as --bad, investigating as
// --warn (in progress, not yet resolved), fixed as --ok.
const STATUS_PILL_CLASS = { open: "pill-bad", investigating: "pill-warn", fixed: "pill-ok" };
const STATUS_LABEL = { open: "open", investigating: "investigating", fixed: "fixed" };

function statusPill(status) {
  const cls = STATUS_PILL_CLASS[status] || "pill-warn";
  const label = STATUS_LABEL[status] || status;
  return `<span class="pill ${cls}">${escapeHtml(label)}</span>`;
}

// Area-card summary badge: one small pill per non-empty bucket, in a
// fixed open → investigating → fixed order so cards stay visually
// comparable across the overview grid. `breakdown` can be undefined for
// an older cached response shape — render nothing rather than throw.
function renderStatusBreakdownPills(breakdown, rowClass) {
  if (!breakdown) return "";
  const order = ["open", "investigating", "fixed"];
  const pills = order
    .filter((status) => breakdown[status] > 0)
    .map((status) => `<span class="pill ${STATUS_PILL_CLASS[status]}">${breakdown[status]} ${STATUS_LABEL[status]}</span>`)
    .join(" ");
  return pills ? `<div class="${rowClass}">${pills}</div>` : "";
}

async function renderOverview(panel) {
  panel.innerHTML = "<p>Loading overview…</p>";
  try {
    const { areas } = await fetchJSON("/api/overview");
    areas.forEach((a) => { state.areaLabels[a.id] = a.label; });
    updateBackButton();
    panel.innerHTML = `<div class="overview-grid">${areas.map(renderAreaCard).join("")}</div>`;
    attachAreaCardHandlers(panel);
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load overview: ${escapeHtml(err.message)}</p>`;
  }
}

// The area card's own click-through target is #area/<id> — but the card
// also contains a real nested link (the "Last run" RUN-xx code). HTML
// doesn't allow an <a> inside another <a> (the browser would silently
// close the outer one, breaking the whole card's layout), so the card is
// a plain div with a delegated click handler instead: clicks on the
// nested run link behave normally (and are left alone here), everything
// else on the card navigates to the area page. role="link" + tabindex
// gives it the same keyboard/AT affordances a real link would have.
function attachAreaCardHandlers(panel) {
  panel.querySelectorAll(".area-card").forEach((card) => {
    const go = () => {
      location.hash = `area/${encodeURIComponent(card.dataset.areaId)}`;
    };
    card.addEventListener("click", (e) => {
      if (e.target.closest("a")) return; // let the nested run-code link navigate itself
      go();
    });
    card.addEventListener("keydown", (e) => {
      if (e.target !== card) return; // don't hijack Enter on the nested link
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        go();
      }
    });
  });
}

function renderAreaCard(area) {
  const passRatePct = area.pass_rate == null ? null : Math.round(area.pass_rate * 100);
  const passRatePill =
    passRatePct == null
      ? `<span class="pill muted-cell">No runs</span>`
      : `<span class="pill ${passRatePct === 100 ? "pill-ok" : passRatePct < 70 ? "pill-bad" : "pill-warn"}">${passRatePct}%</span>`;
  // A last_run can itself carry a null run_code — history predating the
  // backfill, or a plain CLI run collect_run.py never minted one for.
  // Never assume it's linkable.
  let lastRunHtml = `<span class="muted-cell">No runs yet</span>`;
  if (area.last_run) {
    const codeHtml = area.last_run.run_code
      ? `<a href="#run/${encodeURIComponent(area.last_run.run_code)}">${escapeHtml(area.last_run.run_code)}</a>`
      : `<span class="muted-cell">unlinked run</span>`;
    lastRunHtml = `${codeHtml} <span class="muted-cell">· ${formatTimestamp(area.last_run.timestamp)}</span>`;
  }
  const flakyHtml = area.flaky_tests.length
    ? `<div class="area-card-row"><span class="area-card-label">Flaky</span></div>
       <ul class="flaky-list">${area.flaky_tests.map((nid) => `<li>${escapeHtml(nid.split("::").pop())}</li>`).join("")}</ul>`
    : "";
  const issueHtml = renderStatusBreakdownPills(area.status_breakdown, "area-card-row");
  // The card itself is the click-through into #area/<id> (its whole
  // surface, not just a sub-element) — everything already on it
  // (pass-rate, last run, flaky tests, issue count) is exactly the
  // entry-point summary the area-detail page then expands on. Can't be a
  // real <a> — it contains a nested "Last run" link, and HTML forbids
  // nesting anchors (see attachAreaCardHandlers above) — so it's a div
  // with role="link" plus a delegated click/keydown handler instead.
  return `
    <div class="card area-card" data-area-id="${escapeAttr(area.id)}" role="link" tabindex="0">
      <div class="area-card-header">
        <h3>${escapeHtml(area.label)}</h3>
        ${passRatePill}
      </div>
      <div class="area-card-row"><span class="area-card-label">Last run</span> ${lastRunHtml}</div>
      ${flakyHtml}
      ${issueHtml}
    </div>`;
}

// Clicking a findings link switches to the Findings tab. When the button
// also carries `data-issue-title` (the area-detail page's per-issue "See
// in Findings" button — one specific known issue, not the whole callout),
// scroll straight to that entry's own heading instead of leaving the
// reader to hunt through the whole rendered doc for it. The run-detail
// page's callout button has no single title (it can list several
// possible matches at once) and keeps the plain "land on the tab" behavior.
// One delegated listener covers both, regardless of how many times either
// panel gets re-rendered.
document.addEventListener("click", (e) => {
  const btn = e.target.closest('[data-jump="findings"]');
  if (!btn) return;
  e.preventDefault();
  const issueTitle = btn.dataset.issueTitle;
  // pushState, not a hash assignment: the hashchange render would race
  // the scroll below. Recorded by hand for the same reason.
  history.pushState(null, "", "#findings");
  recordNavigation();
  showPage("findings").then(() => {
    if (!issueTitle) return;
    scrollToFindingsHeading(issueTitle);
  });
});

// Finds the `###`-heading (rendered as an <h3>) in the Findings tab whose
// text matches a known issue's title and scrolls it into view. Markdown
// rendering assigns no `id`/anchor to headings, so this matches on the
// heading's own text rather than requiring a server-side slug scheme —
// exact match first (the normal case), falling back to a substring match
// in case the title was ever trimmed/reformatted between the two call
// sites. Silently does nothing if no heading matches (e.g. the issue was
// edited/removed since the area page last loaded) rather than erroring.
function scrollToFindingsHeading(title) {
  // Known issues live in the findings doc, not the investigation log above
  // it — search only there, and expand that section if it's collapsed.
  const section = document.getElementById("all-findings");
  const root = section || document;
  const headings = Array.from(root.querySelectorAll(".findings-content h3"));
  const heading = headings.find((h) => h.textContent.trim() === title.trim()) ||
    headings.find((h) => h.textContent.includes(title) || title.includes(h.textContent.trim()));
  if (!heading) return;
  if (section) section.open = true;
  heading.scrollIntoView({ behavior: "smooth", block: "start" });
  heading.classList.add("findings-heading-highlight");
  setTimeout(() => heading.classList.remove("findings-heading-highlight"), 2000);
}

// --- Area-detail page ---------------------------------------------------------

function renderAreaTestRow(test) {
  const outcomeHtml = test.last_run
    ? outcomePill(test.last_run.outcome, test.last_run.failure_kind)
    : `<span class="pill muted-cell">No runs</span>`;
  const passRatePct = test.pass_rate == null ? null : Math.round(test.pass_rate * 100);
  const passRateHtml =
    passRatePct == null ? "" : `<span class="test-desc">${passRatePct}% of ${test.total_runs}</span>`;
  const linkHtml = test.last_run && test.last_run.run_code
    ? `<a href="#run/${encodeURIComponent(test.last_run.run_code)}">${escapeHtml(test.last_run.run_code)}</a>`
    : `<span class="muted-cell">${test.last_run ? "unlinked run" : "never run"}</span>`;
  return `
    <div class="run-detail-test area-test-row">
      <div class="run-detail-test-top">
        <div>
          <div class="test-name">${escapeHtml(test.name)}</div>
          <div class="test-desc">${escapeHtml(test.file)}</div>
        </div>
        <div class="run-detail-test-actions">
          ${safetyPill(test.safety_marker)}
          ${outcomeHtml}
          ${passRateHtml}
          ${linkHtml}
        </div>
      </div>
    </div>`;
}

function renderAreaKnownIssue(issue) {
  const connected = issue.connected_tests || [];
  const connectedHtml = connected.length
    ? `<ul class="area-issue-connected-list">
        ${connected
          .map((c) => {
            const nameHtml = escapeHtml(c.nodeid.split("::").pop());
            const runHtml = c.run_code
              ? `<a href="#run/${encodeURIComponent(c.run_code)}">${escapeHtml(c.run_code)}</a>`
              : `<span class="muted-cell">unlinked run</span>`;
            return `<li>
              ${outcomePill(c.outcome, c.failure_kind)}
              ${nameHtml} — ${runHtml}
              <span class="test-desc">${formatTimestamp(c.timestamp)}</span>
            </li>`;
          })
          .join("")}
      </ul>`
    : `<p class="test-desc">No test run in this area has failed with a matching signature yet.</p>`;
  return `
    <div class="card area-issue-card" data-issue-status="${escapeAttr(issue.status)}">
      <div class="area-issue-card-title-row">
        <div class="known-issue-callout-title">${escapeHtml(issue.title)}</div>
        ${statusPill(issue.status)}
      </div>
      <p class="test-desc">${escapeHtml(issue.body)}</p>
      <div class="area-issue-connected-title">Connected test runs</div>
      ${connectedHtml}
      <button type="button" class="link-button" data-jump="findings" data-issue-title="${escapeAttr(issue.title)}">See in Findings →</button>
    </div>`;
}

function renderAreaDetailContent(area) {
  const passRatePct = area.pass_rate == null ? null : Math.round(area.pass_rate * 100);
  const passRatePill =
    passRatePct == null
      ? `<span class="pill muted-cell">No runs</span>`
      : `<span class="pill ${passRatePct === 100 ? "pill-ok" : passRatePct < 70 ? "pill-bad" : "pill-warn"}">${passRatePct}%</span>`;
  const lastRunHtml = area.last_run
    ? `${
        area.last_run.run_code
          ? `<a href="#run/${encodeURIComponent(area.last_run.run_code)}">${escapeHtml(area.last_run.run_code)}</a>`
          : `<span class="muted-cell">unlinked run</span>`
      } <span class="muted-cell">· ${formatTimestamp(area.last_run.timestamp)}</span>`
    : `<span class="muted-cell">No runs yet</span>`;

  const fixedCount = (area.status_breakdown && area.status_breakdown.fixed) || 0;
  const issuesHtml = area.known_issues.length
    ? area.known_issues.map(renderAreaKnownIssue).join("")
    : `<p class="test-desc">No confirmed product issues recorded for this area.</p>`;
  // Fixed issues are rendered (so the toggle below can reveal them
  // in-place with no re-fetch) but start hidden — the default view is
  // open/investigating only, so a settled bug doesn't clutter what's
  // still actionable. Only offer the toggle when there's something for
  // it to reveal.
  const issuesFilterHtml = fixedCount
    ? `<label class="field-checkbox area-issues-filter">
         <input type="checkbox" id="show-fixed-issues-toggle">
         Show fixed issues (${fixedCount})
       </label>`
    : "";

  const testsHtml = area.tests.length
    ? area.tests.map(renderAreaTestRow).join("")
    : `<p class="test-desc">No tests found in this area's catalog.</p>`;

  return `
    <div class="breadcrumb-row breadcrumb-end">
      <a href="#tests/${encodeURIComponent(area.id)}">Run these tests →</a>
    </div>
    <div class="card run-header">
      <div class="run-header-top">
        <h2>${escapeHtml(area.label)}</h2>
        ${passRatePill}
      </div>
      <dl class="run-meta">
        <div><dt>Last run</dt><dd>${lastRunHtml}</dd></div>
        <div><dt>Confirmed issues</dt><dd>${area.confirmed_issue_count}</dd></div>
        <div><dt>Flaky tests</dt><dd>${area.flaky_tests.length}</dd></div>
        <div><dt>Tests in area</dt><dd>${area.tests.length}</dd></div>
      </dl>
      ${renderStatusBreakdownPills(area.status_breakdown, "area-card-row")}
    </div>
    <h3 class="run-detail-section-title">Confirmed known issues</h3>
    ${issuesFilterHtml}
    ${issuesHtml}
    <h3 class="run-detail-section-title">Tests in this area</h3>
    <div class="run-detail-tests">${testsHtml}</div>
  `;
}

// Fixed-issue cards are already in the DOM (see renderAreaDetailContent) —
// toggling just flips their `hidden` attribute, no re-render/re-fetch.
// Defaults unchecked (fixed issues hidden) on every fresh render of this
// page, matching "open/investigating is the default view."
function attachAreaIssuesFilter(panel) {
  const toggle = panel.querySelector("#show-fixed-issues-toggle");
  if (!toggle) return;
  const fixedCards = panel.querySelectorAll('.area-issue-card[data-issue-status="fixed"]');
  fixedCards.forEach((card) => { card.hidden = true; });
  toggle.addEventListener("change", () => {
    fixedCards.forEach((card) => { card.hidden = !toggle.checked; });
  });
}

async function renderAreaDetail(panel, areaId) {
  panel.innerHTML = "<p>Loading area…</p>";
  try {
    const area = await fetchJSON(`/api/areas/${encodeURIComponent(areaId)}`);
    panel.innerHTML = renderAreaDetailContent(area);
    attachAreaIssuesFilter(panel);
  } catch (err) {
    // Covers the backend's 404 ("Unknown area: ...") and any other fetch
    // failure alike — same not-found-with-a-way-back pattern as
    // renderRunDetail's catch block.
    panel.innerHTML = `
      <div class="card run-not-found">
        <h2>Area not found</h2>
        <p class="test-desc">${escapeHtml(err.message)}</p>
      </div>`;
  }
}

function showAreaDetailPage(areaId) {
  document.getElementById("nav-overview").classList.remove("active");
  document.getElementById("nav-tests").classList.remove("active");
  document.getElementById("nav-results").classList.remove("active");
  document.getElementById("nav-findings").classList.remove("active");
  document.getElementById("module-tabs").hidden = true;
  renderAreaDetail(document.getElementById("module-panel"), areaId);
}

// --- Run-detail page ---------------------------------------------------------

function formatDuration(seconds) {
  return typeof seconds === "number" ? `${seconds.toFixed(1)}s` : "—";
}

function renderKnownIssueMatches(matches) {
  if (!matches || matches.length === 0) return "";
  const items = matches
    .map((m) => `<li><span class="pill pill-warn">possibly related</span> ${escapeHtml(m.title)}</li>`)
    .join("");
  return `
    <div class="known-issue-callout">
      <div class="known-issue-callout-title">Possible known issues</div>
      <p class="test-desc">
        Keyword overlap only — not a confirmed link. Review before assuming this is the same bug.
      </p>
      <ul>${items}</ul>
      <button type="button" class="link-button" data-jump="findings">See confirmed issues in Findings →</button>
    </div>`;
}

// --- Measurements (run_metrics.py) ---------------------------------------
//
// Tests that use the run_metrics fixture carry `metrics` in history:
// expected-vs-measured checks, plus per run the NTG's saved run (via its
// API) and the WAN emulator's counters. Per-second series live in the
// sidecar file at `metrics_file` and are fetched when the page renders.

const FRAME_AGREEMENT = 0.005; // same 0.5 % allowance T15 uses

function fmtNum(v, digits = 0) {
  if (typeof v !== "number" || !isFinite(v)) return "—";
  return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtCheckValue(v, unit) {
  if (typeof v === "string") return escapeHtml(v); // e.g. a verdict: "pass" / "fail"
  const digits = unit === "frames" ? 0 : unit === "Mbps" ? 1 : 3;
  return `${fmtNum(v, digits)}${unit && unit !== "frames" ? ` ${escapeHtml(unit)}` : ""}`;
}

function checkPill(c) {
  if (c.enforced) return c.ok ? `<span class="pill pill-ok">✓ Pass</span>` : `<span class="pill pill-bad">✗ Fail</span>`;
  return c.ok
    ? `<span class="pill pill-ok">✓ Info · matches</span>`
    : `<span class="pill pill-warn">! Info · off</span>`;
}

function renderChecksTable(checks) {
  if (!checks || checks.length === 0) return "";
  const rows = checks
    .map((c) => {
      const isMin = c.kind === "min";
      const delta =
        !isMin && typeof c.measured === "number" && typeof c.expected === "number" ? c.measured - c.expected : null;
      const tol = isMin
        ? "—"
        : typeof c.tolerance === "number"
          ? `± ${fmtCheckValue(c.tolerance, c.unit)}`
          : "exact";
      return `<tr class="${!c.ok ? "row-bad" : ""}">
        <td>${escapeHtml(c.name)}</td>
        <td class="num">${isMin ? "≥ " : ""}${fmtCheckValue(c.expected, c.unit)}</td>
        <td class="num">${fmtCheckValue(c.measured, c.unit)}</td>
        <td class="num">${delta === null ? "—" : (delta > 0 ? "+" : "") + fmtCheckValue(delta, c.unit)}</td>
        <td class="num">${tol}</td>
        <td>${checkPill(c)}</td>
      </tr>`;
    })
    .join("");
  return `
    <h4>Expected vs measured</h4>
    <table class="metrics-table">
      <thead><tr><th>Check</th><th class="num">Expected</th><th class="num">Measured</th>
        <th class="num">Δ</th><th class="num">Tolerance</th><th>Result</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="metrics-note">"Info" checks are recorded but don't fail the test yet.</p>`;
}

// NTG directions, summed over streams, ordered low port → high port. The
// emulator's a-to-b is its first port → second, cabled to the lower NTG
// port, so index 0 pairs with a-to-b (confirmed by frame counts, 2026-10-05).
function ntgDirections(ntg) {
  const byKey = new Map();
  for (const d of (ntg && ntg.direction) || []) {
    const key = `${d["from-port"]}→${d["to-port"]}`;
    const acc = byKey.get(key) || { from: d["from-port"], to: d["to-port"], tx: 0, rx: 0, dropped: 0, latency: d["avg-latency"] };
    acc.tx += d["tx-frames"] || 0;
    acc.rx += d["rx-frames"] || 0;
    acc.dropped += d.dropped || 0;
    byKey.set(key, acc);
  }
  return [...byKey.values()].sort((a, b) => a.from - b.from);
}

const EMULATOR_DIRECTIONS = ["a-to-b", "b-to-a"];

function renderWitnessTable(run) {
  const dirs = ntgDirections(run.ntg);
  if (dirs.length === 0) return "";
  const delta = (run.wan && run.wan.delta) || {};
  const rows = dirs
    .map((d, i) => {
      const emu = delta[EMULATOR_DIRECTIONS[i]] || {};
      const carried = emu.frames;
      // Bypass has no impairment or queue counters: show "—", not 0.
      const dropped = emu.wan
        ? (emu.wan.drops || 0) + (emu.inflow && emu.inflow.queue ? emu.inflow.queue.drops || 0 : 0)
        : null;
      // The emulator's `frames` are frames it delivered: they match what
      // the NTG received (its drops are the difference to what was sent).
      const agrees = typeof carried === "number" && Math.abs(carried - d.rx) <= Math.max(d.rx * FRAME_AGREEMENT, 10);
      const agreeCell =
        typeof carried !== "number"
          ? `<span class="muted-cell">—</span>`
          : agrees
            ? `<span class="pill pill-ok">✓ match</span>`
            : `<span class="pill pill-bad">✗ off by ${fmtNum(carried - d.rx)}</span>`;
      return `<tr class="${typeof carried === "number" && !agrees ? "row-bad" : ""}">
        <td>Port ${escapeHtml(String(d.from))} → ${escapeHtml(String(d.to))}</td>
        <td class="num">${fmtNum(d.tx)}</td>
        <td class="num">${fmtNum(d.rx)}</td>
        <td class="num">${fmtNum(d.dropped)}</td>
        <td class="num">${fmtNum(d.latency / 1000, 3)} ms</td>
        <td class="num">${fmtNum(carried)}</td>
        <td class="num">${dropped === null ? "—" : fmtNum(dropped)}</td>
        <td>${agreeCell}</td>
      </tr>`;
    })
    .join("");
  return `
    <table class="metrics-table">
      <thead><tr><th>Direction</th><th class="num">NTG sent</th><th class="num">NTG received</th>
        <th class="num">NTG lost</th><th class="num">NTG avg latency</th>
        <th class="num">Emulator delivered</th><th class="num">Emulator dropped</th><th>Counts agree</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderPortRateTable(ntg) {
  const configured = (ntg && ntg["configured-ports"]) || [];
  if (configured.length === 0) return "";
  const actual = new Map(((ntg && ntg.port) || []).map((p) => [p["port-id"], p]));
  const rows = configured
    .map((c) => {
      const p = actual.get(c["port-id"]) || {};
      const share = c["rate-mbps"] ? p["avg-tx-rate"] / c["rate-mbps"] : null;
      const low = typeof share === "number" && share < 0.85;
      return `<tr class="${low ? "row-bad" : ""}">
        <td>Port ${escapeHtml(String(c["port-id"]))}</td>
        <td class="num">${fmtNum(c["rate-mbps"], 0)} Mbps</td>
        <td class="num">${fmtNum(p["avg-tx-rate"], 1)} Mbps</td>
        <td class="num">${fmtNum(p["avg-rx-rate"], 1)} Mbps</td>
        <td class="num">${typeof share === "number" ? fmtNum(share * 100, 0) + " %" : "—"}</td>
        <td>${typeof share !== "number" ? "" : low ? `<span class="pill pill-bad">✗ under rate</span>` : `<span class="pill pill-ok">✓ ok</span>`}</td>
      </tr>`;
    })
    .join("");
  return `
    <table class="metrics-table">
      <thead><tr><th>NTG port</th><th class="num">Configured</th><th class="num">Avg TX</th>
        <th class="num">Avg RX</th><th class="num">TX of configured</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="metrics-note">Averages include the ramps, so a healthy port reads a little under 100 %.</p>`;
}

function renderRunMeta(run) {
  const ntg = run.ntg || {};
  const st = ntg.stages || {};
  const phases = [
    ["ramp up", st["ramp-up-sec"]],
    ["main", st["main-sec"]],
    ["ramp down", st["ramp-down-sec"]],
    ["tail", st["tail-sec"]],
  ]
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => `${k} ${fmtNum(v, 1)} s`)
    .join(" · ");
  const parts = [
    ntg.number !== undefined ? `NTG run #${escapeHtml(String(ntg.number))}` : null,
    ntg["end-reason"] ? `ended: ${escapeHtml(ntg["end-reason"])}` : null,
    ntg["tail-not-settled"] ? `<strong>tail not settled</strong>` : null,
    phases || null,
    run.wan ? `emulator path “${escapeHtml(run.wan.path)}”` : null,
    run.wan && run.wan.buffers ? `emulator buffer failures ${fmtNum(run.wan.buffers.failures)}` : null,
  ].filter(Boolean);
  return `<div class="metrics-run-meta">${parts.join(" · ")}</div>`;
}

function describeImpairment(imp) {
  if (!imp) return "";
  const dirs = EMULATOR_DIRECTIONS.filter((d) => imp[d])
    .map((d) => `${d}: ${Object.entries(imp[d]).map(([k, v]) => `${k} ${v}`).join(", ")}`)
    .join(" · ");
  return `<div class="metrics-impairment">WAN emulator engine ${escapeHtml(String(imp.engine ?? "?"))},
    path “${escapeHtml(imp.path || "?")}” — ${escapeHtml(dirs)}</div>`;
}

// The NTG-only view of a run, for tests that don't go through the WAN
// emulator: the same totals the NTG dashboard's "Expand details" panel shows.
function renderNtgSummary(ntg) {
  const s = (ntg && ntg.summary) || {};
  if (Object.keys(s).length === 0) return "";
  const ms = (us) => (typeof us === "number" ? `${fmtNum(us / 1000, 3)} ms` : "—");
  const verdict = ntg.verdict
    ? `<span class="pill ${ntg.verdict === "pass" ? "pill-ok" : "pill-bad"}">${escapeHtml(ntg.verdict.toUpperCase())}</span>`
    : "";
  const criteria = ntg.criteria ? "" : ` <span class="muted-cell">(no pass criteria set on the NTG)</span>`;
  return `
    <div class="metrics-run-meta">NTG verdict ${verdict}${criteria}</div>
    <table class="metrics-table">
      <thead><tr><th class="num">Avg TX</th><th class="num">Avg RX</th><th class="num">Frames sent</th>
        <th class="num">Frames received</th><th class="num">Loss</th><th class="num">Avg latency</th>
        <th class="num">Min / max latency</th><th class="num">Avg jitter</th></tr></thead>
      <tbody><tr>
        <td class="num">${fmtNum(s["tx-rate"], 1)} Mbps</td>
        <td class="num">${fmtNum(s["rx-rate"], 1)} Mbps</td>
        <td class="num">${fmtNum(s["tx-frames"])}</td>
        <td class="num">${fmtNum(s["rx-frames"])}</td>
        <td class="num">${fmtNum(s["loss-pct"], 3)} %</td>
        <td class="num">${ms(s["avg-latency"])}</td>
        <td class="num">${ms(s["min-latency"])} / ${ms(s["max-latency"])}</td>
        <td class="num">${ms(s["avg-jitter"])}</td>
      </tr></tbody>
    </table>`;
}

function renderNtgDirections(ntg) {
  const dirs = ntgDirections(ntg);
  if (dirs.length === 0) return "";
  const rows = dirs
    .map(
      (d) => `<tr class="${d.dropped ? "row-bad" : ""}">
        <td>Port ${escapeHtml(String(d.from))} → ${escapeHtml(String(d.to))}</td>
        <td class="num">${fmtNum(d.tx)}</td>
        <td class="num">${fmtNum(d.rx)}</td>
        <td class="num">${fmtNum(d.dropped)}</td>
        <td class="num">${fmtNum(d.latency / 1000, 3)} ms</td>
      </tr>`
    )
    .join("");
  return `
    <table class="metrics-table">
      <thead><tr><th>Direction</th><th class="num">Sent</th><th class="num">Received</th>
        <th class="num">Lost</th><th class="num">Avg latency</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function describeUnit(unit) {
  if (!unit) return "";
  const parts = [unit.model, unit.version && `firmware ${unit.version}`, unit.target].filter(Boolean);
  return `<div class="metrics-run-meta">Unit: ${escapeHtml(parts.join(" · "))}</div>`;
}

function renderMetrics(test) {
  const m = test.metrics;
  if (!m) return "";
  const runs = (m.runs || [])
    .map((r) =>
      r.wan
        ? `
      <h4>${escapeHtml(r.label)} run: what each box counted</h4>
      ${renderRunMeta(r)}
      ${renderWitnessTable(r)}
      ${renderPortRateTable(r.ntg)}`
        : `
      <h4>${escapeHtml(r.label)} run: what the NTG measured</h4>
      ${renderRunMeta(r)}
      ${renderNtgSummary(r.ntg)}
      ${renderNtgDirections(r.ntg)}
      ${renderPortRateTable(r.ntg)}`
    )
    .join("");
  const charts = test.metrics_file
    ? `<h4>Per second</h4>
       <div class="metrics-charts" data-metrics-file="${escapeAttr(test.metrics_file)}">
         <p class="test-desc">Loading per-second data…</p></div>`
    : "";
  return `
    <div class="metrics">
      ${describeUnit(m.unit)}
      ${describeImpairment(m.impairment)}
      ${renderChecksTable(m.checks)}
      ${runs}
      ${charts}
    </div>`;
}

// --- Line chart (inline SVG, no library) ---------------------------------
//
// series: [{name, color: "var(--series-1)", dash: bool, points: [[x, y], …]}]
// Thin 2px lines, recessive grid, legend with line keys, end labels,
// crosshair + one tooltip listing every series, and a data-table toggle.

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function lineKey(color, dash) {
  const s = svgEl("svg", { width: 16, height: 8, "aria-hidden": "true" });
  s.appendChild(svgEl("line", { x1: 0, y1: 4, x2: 16, y2: 4, stroke: color, "stroke-width": 2, "stroke-dasharray": dash ? "4 3" : "" }));
  return s;
}

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function fmtTick(v) {
  return Math.abs(v) >= 100 ? fmtNum(v, 0) : Math.abs(v) >= 10 ? fmtNum(v, 1).replace(/\.0$/, "") : String(+v.toFixed(2));
}

function lineChart({ title, sub, unit, series }) {
  series = series.filter((s) => s.points.length > 0);
  const card = document.createElement("div");
  card.className = "chart-card";
  const t = document.createElement("div");
  t.className = "chart-title";
  t.textContent = title;
  card.appendChild(t);
  if (sub) {
    const s = document.createElement("div");
    s.className = "chart-sub";
    s.textContent = sub;
    card.appendChild(s);
  }
  if (series.length === 0) {
    const p = document.createElement("p");
    p.className = "test-desc";
    p.textContent = "No data recorded.";
    card.appendChild(p);
    return card;
  }
  if (series.length > 1) {
    const legend = document.createElement("div");
    legend.className = "chart-legend";
    for (const s of series) {
      const item = document.createElement("span");
      item.appendChild(lineKey(s.color, s.dash));
      item.appendChild(document.createTextNode(s.name));
      legend.appendChild(item);
    }
    card.appendChild(legend);
  }

  const W = 360, H = 160, L = 42, R = 70, T = 18, B = 20;
  const xs = series.flatMap((s) => s.points.map((p) => p[0]));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const yMax = niceMax(Math.max(...series.flatMap((s) => s.points.map((p) => p[1]))));
  const sx = (x) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - R);
  const sy = (y) => T + (1 - y / yMax) * (H - T - B);

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg", role: "img", tabindex: "0" });
  svg.setAttribute("aria-label", `${title}. ${series.map((s) => s.name).join(", ")}. Use "Show data" for values.`);
  for (let i = 0; i <= 4; i++) {
    const v = (yMax * i) / 4, y = sy(v);
    svg.appendChild(svgEl("line", { x1: L, x2: W - R, y1: y, y2: y, class: "grid" }));
    const lbl = svgEl("text", { x: L - 6, y: y + 3.5, "text-anchor": "end", class: "axis-label" });
    lbl.textContent = fmtTick(v);
    svg.appendChild(lbl);
  }
  const unitLbl = svgEl("text", { x: L - 6, y: 9, "text-anchor": "end", class: "axis-label" });
  unitLbl.textContent = unit;
  svg.appendChild(unitLbl);
  for (const xv of [x0, (x0 + x1) / 2, x1]) {
    const lbl = svgEl("text", { x: sx(xv), y: H - 5, "text-anchor": "middle", class: "axis-label" });
    lbl.textContent = `${fmtNum(xv, 0)} s`;
    svg.appendChild(lbl);
  }
  for (const s of series) {
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
    svg.appendChild(svgEl("path", {
      d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
      "stroke-dasharray": s.dash ? "5 4" : "",
    }));
  }
  // End labels, nudged apart (upward, so they never reach the x-axis
  // labels) when lines end close together.
  const ends = series
    .map((s) => ({ s, y: sy(s.points[s.points.length - 1][1]) }))
    .sort((a, b) => b.y - a.y);
  ends.forEach((e, i) => {
    e.y = Math.min(e.y, H - B - 4, i ? ends[i - 1].y - 12 : Infinity);
  });
  for (const e of ends) {
    const lbl = svgEl("text", { x: W - R + 6, y: e.y + 3.5, class: "end-label" });
    lbl.textContent = e.s.name;
    svg.appendChild(lbl);
  }

  const cross = svgEl("line", { y1: T, y2: H - B, class: "crosshair", visibility: "hidden" });
  svg.appendChild(cross);
  const tip = document.createElement("div");
  tip.className = "chart-tooltip";
  tip.hidden = true;
  const nearest = (pts, x) => pts.reduce((a, p) => (Math.abs(p[0] - x) < Math.abs(a[0] - x) ? p : a));
  svg.addEventListener("pointermove", (ev) => {
    const box = svg.getBoundingClientRect();
    const px = ((ev.clientX - box.left) / box.width) * W;
    const xv = x0 + ((Math.min(Math.max(px, L), W - R) - L) / (W - L - R)) * (x1 - x0);
    const snapX = nearest(series[0].points, xv)[0];
    cross.setAttribute("x1", sx(snapX));
    cross.setAttribute("x2", sx(snapX));
    cross.setAttribute("visibility", "visible");
    tip.replaceChildren();
    const head = document.createElement("div");
    head.className = "tt-x";
    head.textContent = `${fmtNum(snapX, 1)} s`;
    tip.appendChild(head);
    for (const s of series) {
      const row = document.createElement("div");
      row.className = "tt-row";
      row.appendChild(lineKey(s.color, s.dash));
      const val = document.createElement("strong");
      val.textContent = `${fmtTick(nearest(s.points, snapX)[1])} ${unit}`;
      row.appendChild(val);
      row.appendChild(document.createTextNode(s.name));
      tip.appendChild(row);
    }
    tip.hidden = false;
    const cardBox = card.getBoundingClientRect();
    const left = ev.clientX - cardBox.left + 12;
    tip.style.left = `${Math.min(left, cardBox.width - tip.offsetWidth - 4)}px`;
    tip.style.top = `${ev.clientY - cardBox.top + 12}px`;
  });
  svg.addEventListener("pointerleave", () => {
    cross.setAttribute("visibility", "hidden");
    tip.hidden = true;
  });
  card.appendChild(svg);
  card.appendChild(tip);

  // Table view: every series at the first series' x positions.
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "link-button chart-table-toggle";
  toggle.textContent = "Show data";
  const wrap = document.createElement("div");
  wrap.className = "chart-table-wrap";
  wrap.hidden = true;
  toggle.addEventListener("click", () => {
    if (!wrap.firstChild) {
      const table = document.createElement("table");
      table.className = "metrics-table";
      const hr = table.createTHead().insertRow();
      for (const h of ["Time (s)", ...series.map((s) => `${s.name} (${unit})`)]) {
        const th = document.createElement("th");
        th.className = "num";
        th.textContent = h;
        hr.appendChild(th);
      }
      const body = table.createTBody();
      for (const [x] of series[0].points) {
        const tr = body.insertRow();
        for (const v of [fmtNum(x, 1), ...series.map((s) => fmtTick(nearest(s.points, x)[1]))]) {
          const td = tr.insertCell();
          td.className = "num";
          td.textContent = v;
        }
      }
      wrap.appendChild(table);
    }
    wrap.hidden = !wrap.hidden;
    toggle.textContent = wrap.hidden ? "Show data" : "Hide data";
  });
  card.appendChild(toggle);
  card.appendChild(wrap);
  return card;
}

// The emulator's per-second records are indexed by its own clock, which
// starts before the NTG's run. Align them on the first second either box
// saw traffic; good to about a second.
function emulatorPoints(wanData, direction, metric, startX, scale = 1) {
  const rec = (Array.isArray(wanData) ? wanData : []).find((d) => d.direction === direction && d.metric === metric);
  const rate = (Array.isArray(wanData) ? wanData : []).find((d) => d.direction === direction && d.metric === "overall-rate");
  if (!rec || !rate) return [];
  const first = rate.values.findIndex((v) => v > 0);
  if (first < 0) return [];
  return rec.values.map((v, i) => [startX + (i - first), v * scale]).filter(([x]) => x >= startX - 1);
}

function renderSeriesCharts(record) {
  const charts = [];
  const runs = record.runs || [];
  const colors = ["var(--series-1)", "var(--series-2)"];
  charts.push(
    lineChart({
      title: "Average latency, NTG",
      sub: runs.some((r) => r.wan)
        ? "One line per run; the gap between them is what the emulator added."
        : "Per second, seconds with traffic received.",
      unit: "ms",
      series: runs.slice(0, 2).map((r, i) => ({
        name: r.label,
        color: colors[i],
        // Seconds with nothing received have no latency (the NTG reports
        // 0); leave them out rather than draw a fake drop to zero.
        points: ((r.series && r.series.ntg) || [])
          .filter((s) => s["rx-rate"] > 0)
          .map((s) => [s.at, (s["avg-latency"] || 0) / 1000]),
      })),
    })
  );
  for (const r of runs) {
    const samples = (r.series && r.series.ntg) || [];
    const firstTx = samples.find((s) => s["tx-rate"] > 0);
    const startX = firstTx ? firstTx.at : 0;
    ntgDirections(r.ntg).forEach((d, i) => {
      charts.push(
        lineChart({
          title: `${r.label}: Port ${d.from} → ${d.to} throughput`,
          sub: r.wan
            ? "What the NTG sent vs what the emulator carried; matching lines mean the two boxes agree."
            : "What the sending port transmitted vs what its peer received.",
          unit: "Mbps",
          series: [
            {
              name: "NTG sent",
              color: colors[0],
              points: samples.map((s) => [s.at, ((s.port || []).find((p) => p["port-id"] === d.from) || {})["tx-rate"] || 0]),
            },
            r.wan
              ? {
                  name: "Emulator",
                  color: colors[1],
                  dash: true,
                  points: emulatorPoints(r.series && r.series.wan, EMULATOR_DIRECTIONS[i], "overall-rate", startX, 1e-6),
                }
              : {
                  name: "NTG received",
                  color: colors[1],
                  dash: true,
                  points: samples.map((s) => [s.at, ((s.port || []).find((p) => p["port-id"] === d.to) || {})["rx-rate"] || 0]),
                },
          ],
        })
      );
    });
  }
  return charts;
}

async function loadMetricsCharts(panel) {
  for (const el of panel.querySelectorAll(".metrics-charts[data-metrics-file]")) {
    try {
      const record = await fetchJSON(el.dataset.metricsFile);
      el.replaceChildren(...renderSeriesCharts(record));
    } catch (err) {
      el.innerHTML = `<p class="test-desc">Per-second data unavailable (${escapeHtml(err.message)}). It's kept only on the machine that ran the test.</p>`;
    }
  }
}

function renderRunDetailTestRow(test, run) {
  const areaLabel = test.area
    ? `<a href="#area/${encodeURIComponent(test.area.id)}">${escapeHtml(test.area.label)}</a>`
    : `<span class="muted-cell">Unmapped area</span>`;
  const failureBlock = test.failure_message
    ? `<pre class="run-detail-failure">${escapeHtml(test.failure_message)}</pre>`
    : "";
  const artifacts = [
    test.screenshot ? `<a href="/results/${test.screenshot}" target="_blank">screenshot</a>` : null,
    test.trace ? `<a href="/results/${test.trace}" target="_blank">trace</a>` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="run-detail-test">
      <div class="run-detail-test-top">
        <div>
          <div class="test-name">${escapeHtml(test.nodeid.split("::").pop())}</div>
          <div class="test-desc">${escapeHtml(test.nodeid)}</div>
        </div>
        <div class="run-detail-test-actions">
          ${areaLabel}
          ${outcomePill(test.outcome, test.failure_kind)}
          <span class="test-desc">${formatDuration(test.duration)}</span>
          <button type="button" class="btn-outline rerun-btn"
            data-nodeid="${escapeAttr(catalogNodeid(test.nodeid))}"
            data-marker="${escapeAttr(run.markers || "hardware_free")}">Run again</button>
        </div>
      </div>
      ${artifacts ? `<div class="run-detail-artifacts">${artifacts}</div>` : ""}
      ${failureBlock}
      ${renderKnownIssueMatches(test.known_issue_matches)}
      ${renderMetrics(test)}
    </div>`;
}

function renderSiblingRuns(nodeid, rows) {
  if (!rows || rows.length === 0) return "";
  const items = rows
    .map((r) => {
      // A pre-backfill or CLI-triggered sibling may have no run_code at
      // all — show it as an unlinked entry rather than a broken link.
      const codeHtml = r.run_code
        ? `<a href="#run/${encodeURIComponent(r.run_code)}">${escapeHtml(r.run_code)}</a>`
        : `<span class="muted-cell">unlinked run</span>`;
      return `<li>${codeHtml}
        <span class="test-desc">${formatTimestamp(r.timestamp)}</span>
        ${outcomePill(r.outcome, r.failure_kind)}</li>`;
    })
    .join("");
  return `
    <div class="card sibling-runs-card">
      <div class="test-desc">${escapeHtml(nodeid.split("::").pop())}</div>
      <ul class="sibling-runs-list">${items}</ul>
    </div>`;
}

function renderRunDetailContent(run) {
  const total = run.tests.length;
  const passCount = run.tests.filter((t) => t.outcome === "pass").length;
  const anyFailed = run.tests.some((t) => t.outcome === "fail" || t.outcome === "error");
  const overallClass = total > 0 && passCount === total ? "pill-ok" : anyFailed ? "pill-bad" : "pill-warn";
  const siblingSections = Object.entries(run.sibling_runs || {})
    .map(([nodeid, rows]) => renderSiblingRuns(nodeid, rows))
    .join("");
  return `
    <div class="card run-header">
      <div class="run-header-top">
        <h2>${escapeHtml(run.run_code || run.run_id)}</h2>
        <span class="pill ${overallClass}">${passCount}/${total} passed</span>
        ${run.flaky ? `<span class="pill pill-warn">Flaky</span>` : ""}
      </div>
      <dl class="run-meta">
        <div><dt>Started</dt><dd>${formatTimestamp(run.timestamp)}</dd></div>
        <div><dt>Git</dt><dd>${run.git_sha ? escapeHtml(run.git_sha) : "—"}${run.git_branch ? ` on ${escapeHtml(run.git_branch)}` : ""}</dd></div>
        <div><dt>Markers</dt><dd>${run.markers ? escapeHtml(run.markers) : "—"}</dd></div>
        <div><dt>Duration</dt><dd>${formatDuration(run.duration)}</dd></div>
      </dl>
    </div>
    <h3 class="run-detail-section-title">Tests in this run</h3>
    <div class="run-detail-tests">${run.tests.map((t) => renderRunDetailTestRow(t, run)).join("")}</div>
    ${siblingSections ? `<h3 class="run-detail-section-title">Other runs of these tests</h3>${siblingSections}` : ""}
  `;
}

function attachRunDetailHandlers(panel) {
  panel.querySelectorAll(".rerun-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      openRunModal(btn.dataset.nodeid, btn.dataset.marker, btn);
    });
  });
}

async function renderRunDetail(panel, runCode) {
  panel.innerHTML = "<p>Loading run…</p>";
  try {
    const run = await fetchJSON(`/api/runs/${encodeURIComponent(runCode)}`);
    panel.innerHTML = renderRunDetailContent(run);
    attachRunDetailHandlers(panel);
    loadMetricsCharts(panel);
  } catch (err) {
    // Covers the backend's 404 ("Unknown run: RUN-x") and any other
    // fetch failure alike — a run-detail page that failed to load must
    // never render broken, just a plain not-found-style state with a way
    // back out.
    panel.innerHTML = `
      <div class="card run-not-found">
        <h2>Run not found</h2>
        <p class="test-desc">${escapeHtml(err.message)}</p>
      </div>`;
  }
}

function showRunDetailPage(runCode) {
  document.getElementById("nav-overview").classList.remove("active");
  document.getElementById("nav-tests").classList.remove("active");
  document.getElementById("nav-results").classList.remove("active");
  document.getElementById("nav-findings").classList.remove("active");
  document.getElementById("module-tabs").hidden = true;
  renderRunDetail(document.getElementById("module-panel"), runCode);
}

// --- Back navigation ---------------------------------------------------------
//
// Every page is a hash route, so the browser's history is the app's. navStack
// mirrors the part of it made inside the dashboard: while it has an earlier
// page, Back is history.back() (one step, to wherever you came from). A page
// opened directly (a shared link, a reload) has none, so Back goes to its
// parent instead: Results for a run, Overview for an area, the cards for a
// test area. No parent and no history: no Back button.
const navStack = [location.hash || "#tests"];

function recordNavigation() {
  const hash = location.hash || "#tests";
  if (navStack.length > 1 && navStack[navStack.length - 2] === hash) {
    navStack.pop();               // a browser/Back step to the previous page
  } else if (navStack[navStack.length - 1] !== hash) {
    navStack.push(hash);
  }
  updateBackButton();
}

function parentOf(hash) {
  if (/^#run\//.test(hash)) return "#results";
  if (/^#area\//.test(hash)) return "#overview";
  if (/^#tests\/./.test(hash)) return "#tests";
  return null;
}

function pageLabel(hash) {
  const route = hash.slice(1);
  if (!route || route === "tests") return "Tests";
  const area = (id) => state.areaLabels[id] || id;
  if (route.startsWith("tests/")) return `${area(decodeURIComponent(route.slice(6)))} tests`;
  if (route.startsWith("run/")) return decodeURIComponent(route.slice(4));
  if (route.startsWith("area/")) return area(decodeURIComponent(route.slice(5)));
  return route.charAt(0).toUpperCase() + route.slice(1);
}

function backTarget() {
  const current = navStack[navStack.length - 1];
  return navStack.length > 1 ? navStack[navStack.length - 2] : parentOf(current);
}

function updateBackButton() {
  const btn = document.getElementById("nav-back");
  const target = backTarget();
  btn.hidden = !target;
  if (target) {
    const label = `Back to ${pageLabel(target)}`;
    btn.title = label;
    btn.setAttribute("aria-label", label);
  }
}

document.getElementById("nav-back").addEventListener("click", () => {
  if (navStack.length > 1) {
    history.back();
  } else {
    const parent = parentOf(navStack[0]);
    if (parent) location.hash = parent.slice(1);
  }
});

// --- Minimal hash routing ----------------------------------------------------
//
// No general router: each page is one hash pattern (#overview, #tests,
// #tests/<area>, #results, #findings, #run/<code>, #area/<id>), so every
// page can be linked to and is a browser-history entry (see Back above).

function parseHash() {
  const hash = location.hash.slice(1);
  if (!hash) return null;
  const runMatch = hash.match(/^run\/(.+)$/);
  if (runMatch) return { page: "run", code: decodeURIComponent(runMatch[1]) };
  const areaMatch = hash.match(/^area\/(.+)$/);
  if (areaMatch) return { page: "area", id: decodeURIComponent(areaMatch[1]) };
  if (hash === "overview") return { page: "overview" };
  if (hash === "results") return { page: "results" };
  if (hash === "findings") return { page: "findings" };
  if (hash === "tests") return { page: "tests", area: null };
  const testsMatch = hash.match(/^tests\/(.+)$/);
  if (testsMatch) return { page: "tests", area: decodeURIComponent(testsMatch[1]) };
  return null;
}

// Opening the cards or an area starts from an unfiltered view (a search
// would otherwise hide the area that was just asked for). Selections are
// kept, so tests can be picked across areas and run together.
function openTestsView(area) {
  state.testsView = { area, query: "", filter: "all" };
  const onTests = document.getElementById("nav-tests").classList.contains("active")
    && document.getElementById("tests-body");
  if (onTests) {
    syncTestsToolbar();
    renderTestsBody();
    window.scrollTo(0, 0);
  } else {
    showPage("tests");
  }
}

function handleHashChange() {
  recordNavigation();
  const route = parseHash();
  if (!route) return;
  if (route.page === "overview" || route.page === "results" || route.page === "findings") {
    showPage(route.page);
  } else if (route.page === "run") {
    showRunDetailPage(route.code);
  } else if (route.page === "area") {
    showAreaDetailPage(route.id);
  } else if (route.page === "tests") {
    openTestsView(route.area);
  }
}

window.addEventListener("hashchange", handleHashChange);

async function renderFindings(panel) {
  panel.innerHTML = "<p>Loading findings…</p>";
  try {
    const { html, investigation_html: investigationHtml } = await fetchJSON("/api/findings");
    // The ongoing investigation write-up (docs/ntg5-investigation-log.md)
    // sits above the full findings doc, open by default.
    const investigation = investigationHtml
      ? `<details class="findings-section" open>
           <summary>Current investigation — NTG 5.0 (ongoing log)</summary>
           <div class="findings-content">${investigationHtml}</div>
         </details>`
      : "";
    panel.innerHTML = `${investigation}
      <details class="findings-section" id="all-findings" ${investigationHtml ? "" : "open"}>
        <summary>All findings</summary>
        <div class="findings-content">${html}</div>
      </details>`;
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load findings: ${escapeHtml(err.message)}</p>`;
  }
}

// --- Results page: every run, newest first, grouped by day -------------------
//
// One entry per run (a history file: a dashboard run or a command-line
// pytest session). The newest is open; older ones are collapsed and load
// their tests from /api/history/<run_id> the first time they're opened.

async function renderResults(panel) {
  panel.innerHTML = "<p>Loading results…</p>";
  try {
    const { sessions } = await fetchJSON("/api/history");
    if (sessions.length === 0) {
      panel.innerHTML = `<p class="test-desc">No runs yet — go run a test from the Tests page.</p>`;
      return;
    }
    panel.innerHTML = `
      <div class="filter-field">
        <input type="search" id="results-filter" class="filter-input"
          placeholder="Search runs: code, date, box, marker, or a test that didn't pass…" aria-label="Search runs">
      </div>
      <div id="results-list">${renderSessionDays(sessions)}</div>
      <p id="results-filter-empty" class="test-desc" hidden>No runs match.</p>`;
    attachResultsHandlers(panel);
    const newest = panel.querySelector(".history-run");
    if (newest) {
      newest.open = true;
      loadSessionTests(newest);
    }
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load results: ${escapeHtml(err.message)}</p>`;
  }
}

function localDayKey(ts) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function dayHeading(ts) {
  const d = new Date(ts);
  const full = d.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (localDayKey(d) === localDayKey(today)) return `Today · ${full}`;
  if (localDayKey(d) === localDayKey(yesterday)) return `Yesterday · ${full}`;
  return full;
}

function renderSessionDays(sessions) {
  const days = [];
  for (const s of sessions) {
    const key = s.timestamp ? localDayKey(s.timestamp) : "unknown";
    let day = days[days.length - 1];
    if (!day || day.key !== key) {
      day = { key, heading: s.timestamp ? dayHeading(s.timestamp) : "Undated", sessions: [] };
      days.push(day);
    }
    day.sessions.push(s);
  }
  let first = true;
  return days.map((day) => `
    <section class="history-day">
      <h3 class="history-day-heading">${escapeHtml(day.heading)}
        <span class="muted-cell">${day.sessions.length} run${day.sessions.length === 1 ? "" : "s"}</span></h3>
      ${day.sessions.map((s) => { const html = renderSession(s, first); first = false; return html; }).join("")}
    </section>`).join("");
}

function countPills(counts) {
  const order = [["pass", "passed", "pill-ok"], ["fail", "failed", "pill-bad"], ["error", "errors", "pill-bad"], ["skip", "skipped", "pill-muted"]];
  return order
    .filter(([key]) => counts[key] > 0)
    .map(([key, label, cls]) => `<span class="pill ${cls}">${counts[key]} ${label}</span>`)
    .join("");
}

function formatSeconds(seconds) {
  if (typeof seconds !== "number") return "";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  return m < 60 ? `${m}m ${Math.round(seconds % 60)}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function renderSession(s, isNewest) {
  const time = s.timestamp
    ? new Date(s.timestamp).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : "—";
  const code = s.run_code
    ? `<a href="#run/${encodeURIComponent(s.run_code)}">${escapeHtml(s.run_code)}</a>`
    : `<span class="muted-cell">no code</span>`;
  // "not quarantine" is pytest.ini's default filter, i.e. no marker chosen.
  const marker = s.markers && s.markers !== "not quarantine" ? s.markers : "";
  const what = s.total === 1
    ? escapeHtml(s.test_names[0] || "")
    : `${s.total} tests${marker ? ` · ${escapeHtml(marker)}` : ""}`;
  const box = s.target ? `${escapeHtml(s.target.replace(/^https?:\/\//, ""))}${s.target_version ? ` (${escapeHtml(s.target_version)})` : ""}` : "";
  const search = [
    s.run_code, s.timestamp, s.timestamp && dayHeading(s.timestamp), s.markers, s.source, s.target,
    s.target_version, ...s.test_names, ...s.problems.map((p) => `${p.name} ${p.outcome} ${p.reason || ""}`),
  ].join(" ").toLowerCase();
  return `
    <details class="history-run" data-run-id="${escapeAttr(s.run_id || "")}" data-run-code="${escapeAttr(s.run_code || "")}"
      data-search="${escapeAttr(search)}">
      <summary>
        <span class="history-run-main">
          <span class="history-run-code">${code}</span>
          ${isNewest ? `<span class="pill pill-accent">latest</span>` : ""}
          <span class="history-run-time" title="${escapeAttr(formatTimestamp(s.timestamp))}">${time}</span>
          <span class="history-run-what">${what}</span>
        </span>
        <span class="history-run-meta">
          ${countPills(s.counts)}
          <span class="pill pill-muted">${s.source === "dashboard" ? "Dashboard" : "Command line"}</span>
          ${box ? `<span class="muted-cell">${box}</span>` : ""}
          <span class="muted-cell">${formatSeconds(s.duration)}</span>
        </span>
      </summary>
      <div class="history-run-body"><p class="test-desc">Loading tests…</p></div>
    </details>`;
}

async function loadSessionTests(details) {
  if (details.dataset.loaded) return;
  details.dataset.loaded = "1";
  const body = details.querySelector(".history-run-body");
  try {
    const { tests } = await fetchJSON(`/api/history/${encodeURIComponent(details.dataset.runId)}`);
    body.innerHTML = renderSessionTests(tests, details.dataset.runCode);
  } catch (err) {
    body.innerHTML = `<p class="test-desc">Couldn't load this run's tests: ${escapeHtml(err.message)}</p>`;
    delete details.dataset.loaded;
  }
}

// Tests that didn't pass come first, each with the first line of its
// reason (a skip's reason says why it didn't run, e.g. "Engine 2 is in use").
function renderSessionTests(tests, runCode) {
  const rank = { error: 0, fail: 1, skip: 2, pass: 3 };
  const rows = [...tests]
    .sort((a, b) => (rank[a.outcome] ?? 9) - (rank[b.outcome] ?? 9))
    .map((t) => {
      const evidence = [
        t.screenshot ? `<a href="/results/${t.screenshot}" target="_blank">screenshot</a>` : "",
        t.trace ? `<a href="/results/${t.trace}" target="_blank">trace</a>` : "",
      ].filter(Boolean).join(" · ") || `<span class="muted-cell">—</span>`;
      return `<tr>
        <td><div class="test-name">${escapeHtml((t.nodeid || "").split("::").pop())}</div>
          ${t.reason && t.outcome !== "pass" ? `<div class="test-desc">${escapeHtml(t.reason)}</div>` : ""}</td>
        <td>${outcomePill(t.outcome, t.failure_kind)}</td>
        <td class="num">${formatSeconds(t.duration)}</td>
        <td>${evidence}</td>
      </tr>`;
    })
    .join("");
  const details = runCode
    ? `<p class="history-run-link"><a href="#run/${encodeURIComponent(runCode)}">Full run page: measurements, known issues, traces →</a></p>`
    : "";
  return `
    <table class="results-table history-tests">
      <thead><tr><th>Test</th><th>Result</th><th class="num">Duration</th><th>Evidence</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${details}`;
}

function attachResultsHandlers(panel) {
  panel.querySelectorAll(".history-run").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (details.open) loadSessionTests(details);
    });
  });
  const input = panel.querySelector("#results-filter");
  const emptyMsg = panel.querySelector("#results-filter-empty");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    let anyVisible = false;
    panel.querySelectorAll(".history-day").forEach((day) => {
      let dayVisible = false;
      day.querySelectorAll(".history-run").forEach((run) => {
        const match = !q || run.dataset.search.includes(q);
        run.hidden = !match;
        if (match) dayVisible = true;
      });
      day.hidden = !dayVisible;
      if (dayVisible) anyVisible = true;
    });
    emptyMsg.hidden = anyVisible;
  });
}

// Readable local date and time ("Thu, Oct 16, 2026, 3:47 PM PDT") for the
// ISO-8601 UTC timestamps history stores.
function formatTimestamp(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (isNaN(d)) return ts;
  return d.toLocaleString(undefined, {
    weekday: "short", year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
}

updateBackButton();

// Initial load: honor a deep link straight to #overview or #run/<code> if
// one is already in the address bar (e.g. a bookmarked/shared link, or a
// page reload); otherwise this is unchanged from before — just boot the
// Tests tab, which is already marked active in the static HTML.
{
  const initialRoute = parseHash();
  if (initialRoute && initialRoute.page === "overview") {
    showPage("overview");
  } else if (initialRoute && initialRoute.page === "run") {
    showRunDetailPage(initialRoute.code);
  } else if (initialRoute && initialRoute.page === "area") {
    showAreaDetailPage(initialRoute.id);
  } else if (initialRoute && (initialRoute.page === "results" || initialRoute.page === "findings")) {
    showPage(initialRoute.page);
  } else {
    if (initialRoute && initialRoute.page === "tests") state.testsView.area = initialRoute.area;
    loadModules();
  }
}

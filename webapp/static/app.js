// selectedTests: nodeid -> safety_marker, so "Run selected" can compute a
// stateful-count warning without a second lookup against state.catalog.
const state = { catalog: null, liveStatus: {}, batchRunning: false, selectedTests: new Map() };

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
    btn.innerHTML = `<img src="${m.icon}" alt=""><span>${m.name}</span>`;
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
        <img src="${module.icon}" alt="">
        <h2>${module.name}</h2>
        <p>Test coverage for this module hasn't been built yet.</p>
      </div>`;
    return;
  }
  renderTrafficGenerator(panel);
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
    panel.innerHTML = `
      <div class="filter-field">
        <input type="text" id="tests-filter" class="filter-input" placeholder="Search tests…" aria-label="Search tests">
      </div>
      <div id="selection-bar" class="selection-bar" hidden>
        <span id="selection-count"></span>
        <div class="selection-bar-actions">
          <button type="button" class="btn-outline" id="selection-clear">Clear</button>
          <button type="button" class="btn-primary" id="selection-run">Run selected</button>
        </div>
      </div>
      <p id="tests-filter-empty" class="test-desc" hidden>No tests match.</p>
      ${groups.map(renderGroup).join("")}`;
    attachTestRowHandlers();
    attachTestsFilter();
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load tests: ${escapeHtml(err.message)}</p>`;
  }
}

// Client-side filter for the Tests tab — matches test name, nodeid, and
// short/full description against the query (case-insensitive substring).
// Toggles [hidden] on non-matching rows rather than re-rendering the DOM
// tree, and hides a whole group section when none of its rows remain
// visible (a "T5 — Ports" header with nothing under it reads as broken).
function attachTestsFilter() {
  const input = document.getElementById("tests-filter");
  const emptyMsg = document.getElementById("tests-filter-empty");
  if (!input) return;
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    let anyVisible = false;
    document.querySelectorAll(".group").forEach((group) => {
      let groupHasVisible = false;
      group.querySelectorAll(".test-row").forEach((row) => {
        const name = row.querySelector(".test-name")?.textContent || "";
        const shortDesc = row.querySelector(".test-desc")?.textContent || "";
        const nodeid = row.dataset.nodeid || "";
        const fullDesc = row.dataset.fullDescription || "";
        const haystack = `${name} ${nodeid} ${shortDesc} ${fullDesc}`.toLowerCase();
        const match = !q || haystack.includes(q);
        row.hidden = !match;
        if (match) groupHasVisible = true;
      });
      group.hidden = !groupHasVisible;
      if (groupHasVisible) anyVisible = true;
    });
    emptyMsg.hidden = anyVisible;
  });
}

function renderGroup(group) {
  // Same source of truth safetyPill/renderTestRow use for each row's
  // "Generates traffic" pill — reused here so "Run all" and the
  // per-test pills can never disagree about which tests are stateful.
  const allTests = group.files.flatMap((f) => f.tests);
  const statefulCount = allTests.filter((t) => t.safety_marker === "stateful").length;
  const groupName = group.label.split(" — ")[0];
  const rows = group.files
    .flatMap((f) => f.tests.map((t) => renderTestRow(t, f)))
    .join("");
  return `
    <section class="group" data-group-id="${group.id}">
      <div class="group-header">
        <h2>${group.label}</h2>
        <button type="button" class="btn-outline run-all-btn"
          data-nodeids='${JSON.stringify(group.run_all_nodeids)}'
          data-stateful-count="${statefulCount}"
          data-group-name="${escapeAttr(groupName)}">
          Run all in ${groupName}
        </button>
      </div>
      ${rows}
    </section>`;
}

function safetyPill(marker) {
  if (marker === "stateful") return `<span class="pill pill-warn">Generates traffic</span>`;
  return `<span class="pill pill-ok">Safe</span>`;
}

function renderTestRow(test, file) {
  return `
    <div class="test-row" data-nodeid="${test.nodeid}" data-full-description="${escapeAttr(file.full_description)}">
      <div class="test-row-main">
        <input type="checkbox" class="test-select" data-nodeid="${test.nodeid}" data-marker="${test.safety_marker}" aria-label="Select ${escapeAttr(test.name)}">
        <div>
          <div class="test-name">${test.name}</div>
          <div class="test-desc">${file.short_description}</div>
        </div>
      </div>
      <div class="test-row-actions">
        <span class="pill" data-status-for="${test.nodeid}"></span>
        ${safetyPill(test.safety_marker)}
        <button type="button" class="btn-primary run-btn" data-nodeid="${test.nodeid}" data-marker="${test.safety_marker}">Run</button>
      </div>
    </div>`;
}

function escapeAttr(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
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

function attachTestRowHandlers() {
  document.querySelectorAll(".test-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest(".run-btn") || e.target.closest(".test-select")) return;
      toggleDetail(row);
    });
  });
  document.querySelectorAll(".run-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openRunModal(btn.dataset.nodeid, btn.dataset.marker, btn);
    });
  });
  document.querySelectorAll(".run-all-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const nodeids = JSON.parse(btn.dataset.nodeids);
      const statefulCount = parseInt(btn.dataset.statefulCount, 10) || 0;
      if (statefulCount > 0) {
        // At least one stateful test in this group — same hazard as the
        // single-test Run modal's warning, just naming the group instead
        // of one nodeid. Block on confirmation before anything runs.
        openRunAllModal(nodeids, btn.dataset.groupName, statefulCount, btn);
      } else {
        // All hardware_free — no traffic risk, no added friction.
        runAllInGroup(nodeids);
      }
    });
  });
  document.querySelectorAll(".test-select").forEach((cb) => {
    cb.addEventListener("change", () => {
      const nodeid = cb.dataset.nodeid;
      if (cb.checked) state.selectedTests.set(nodeid, cb.dataset.marker);
      else state.selectedTests.delete(nodeid);
      updateSelectionBar();
    });
  });
  document.getElementById("selection-clear")?.addEventListener("click", () => {
    state.selectedTests.clear();
    document.querySelectorAll(".test-select").forEach((cb) => (cb.checked = false));
    updateSelectionBar();
  });
  document.getElementById("selection-run")?.addEventListener("click", () => {
    const nodeids = Array.from(state.selectedTests.keys());
    const statefulCount = Array.from(state.selectedTests.values()).filter(
      (marker) => marker === "stateful"
    ).length;
    openRunSelectedModal(nodeids, statefulCount, document.getElementById("selection-run"));
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

// modalMode distinguishes the three things this one modal now confirms:
// "single" (openRunModal — repeat-count field, calls startRun), "group"
// (openRunAllModal — no repeat count, every test runs once, calls
// runAllInGroup), and "selected" (openRunSelectedModal — repeat count
// applies to EACH selected test, calls runSelectedTests).
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
  if (!alreadyOnTests) await showPage("tests");
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
      body: JSON.stringify({ nodeid, repeat_count: repeatCount, headed }),
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
  const el = document.querySelector(`[data-status-for="${nodeid}"]`);
  // The "View summary →" link (added once a run_code is known, see the
  // batch_complete handler below) lives next to the status pill, inside
  // the same actions container the pill and Run button already share.
  const actionsEl = el ? el.closest(".test-row-actions") : null;
  let lastRunCode = null;
  state.liveStatus[nodeid] = "running";
  state.batchRunning = true;
  setRunControlsEnabled(false);
  // A re-run of the same row must not leave a stale link pointing at the
  // previous run_code visible while this new run is in flight.
  if (actionsEl) {
    const stale = actionsEl.querySelector(".view-summary-link");
    if (stale) stale.remove();
  }
  // Reflect "running" the instant the batch is confirmed started, rather
  // than waiting on the first SSE round-trip (pytest collection can take
  // a beat before the first iteration event arrives).
  if (el) {
    el.textContent = "running";
    el.className = "pill pill-warn";
  }
  const source = new EventSource(`/api/runs/${batchId}/stream`);
  const finish = () => {
    state.batchRunning = false;
    setRunControlsEnabled(true);
  };
  source.onmessage = (e) => {
    const payload = JSON.parse(e.data);
    if (payload.type === "iteration") {
      if (payload.run_code) lastRunCode = payload.run_code;
      if (el) {
        el.textContent = `${payload.status} (${payload.iteration}/${payload.total})`;
        el.className = "pill " + statusPillClass(payload.status);
      }
    } else if (payload.type === "batch_complete") {
      state.liveStatus[nodeid] = "done";
      if (el) el.textContent = `${payload.passed}/${payload.total} passed`;
      // lastRunCode is the most recent iteration's code — for the common
      // repeat_count=1 case that's the only run; for a repeat run it's
      // the last one, which is what "View summary" should point at.
      if (actionsEl && lastRunCode) {
        const link = document.createElement("a");
        link.href = `#run/${encodeURIComponent(lastRunCode)}`;
        link.className = "view-summary-link";
        link.textContent = "View summary →";
        actionsEl.appendChild(link);
      }
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

document.getElementById("nav-tests").addEventListener("click", () => showPage("tests"));
document.getElementById("nav-results").addEventListener("click", () => showPage("results"));
document.getElementById("nav-findings").addEventListener("click", () => showPage("findings"));
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
  return "pill-warn";
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
  const heading = Array.from(document.querySelectorAll(".findings-content h3")).find(
    (h) => h.textContent.trim() === title.trim()
  ) || Array.from(document.querySelectorAll(".findings-content h3")).find(
    (h) => h.textContent.includes(title) || title.includes(h.textContent.trim())
  );
  if (!heading) return;
  heading.scrollIntoView({ behavior: "smooth", block: "start" });
  heading.classList.add("findings-heading-highlight");
  setTimeout(() => heading.classList.remove("findings-heading-highlight"), 2000);
}

// --- Area-detail page ---------------------------------------------------------

function renderAreaTestRow(test) {
  const outcomeHtml = test.last_run
    ? `<span class="pill ${outcomePillClass(test.last_run.outcome)}">${escapeHtml(test.last_run.outcome)}</span>`
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
              <span class="pill ${outcomePillClass(c.outcome)}">${escapeHtml(c.outcome)}</span>
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
    <div class="breadcrumb-row"><a href="#overview">← Overview</a></div>
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
      <div class="breadcrumb-row"><a href="#overview">← Overview</a></div>
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
          <span class="pill ${outcomePillClass(test.outcome)}">${escapeHtml(test.outcome)}</span>
          <span class="test-desc">${formatDuration(test.duration)}</span>
          <button type="button" class="btn-outline rerun-btn"
            data-nodeid="${escapeAttr(catalogNodeid(test.nodeid))}"
            data-marker="${escapeAttr(run.markers || "hardware_free")}">Run again</button>
        </div>
      </div>
      ${artifacts ? `<div class="run-detail-artifacts">${artifacts}</div>` : ""}
      ${failureBlock}
      ${renderKnownIssueMatches(test.known_issue_matches)}
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
        <span class="pill ${outcomePillClass(r.outcome)}">${escapeHtml(r.outcome)}</span></li>`;
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
    <div class="breadcrumb-row"><a href="#overview">← Overview</a></div>
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
  } catch (err) {
    // Covers the backend's 404 ("Unknown run: RUN-x") and any other
    // fetch failure alike — a run-detail page that failed to load must
    // never render broken, just a plain not-found-style state with a way
    // back out.
    panel.innerHTML = `
      <div class="breadcrumb-row"><a href="#overview">← Overview</a></div>
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

// --- Minimal hash routing ----------------------------------------------------
//
// This app has no general router — only these two addressable states are
// worth a URL: an overview snapshot and a single run's detail page, both
// meant to be shareable/bookmarkable/linkable-to from elsewhere in the
// app. Tests/Results/Findings stay exactly as they were (no hash), driven
// only by their nav buttons like before.

function parseHash() {
  const hash = location.hash.slice(1);
  if (!hash) return null;
  const runMatch = hash.match(/^run\/(.+)$/);
  if (runMatch) return { page: "run", code: decodeURIComponent(runMatch[1]) };
  const areaMatch = hash.match(/^area\/(.+)$/);
  if (areaMatch) return { page: "area", id: decodeURIComponent(areaMatch[1]) };
  if (hash === "overview") return { page: "overview" };
  return null;
}

function handleHashChange() {
  const route = parseHash();
  if (!route) return;
  if (route.page === "overview") {
    showPage("overview");
  } else if (route.page === "run") {
    showRunDetailPage(route.code);
  } else if (route.page === "area") {
    showAreaDetailPage(route.id);
  }
}

window.addEventListener("hashchange", handleHashChange);

async function renderFindings(panel) {
  panel.innerHTML = "<p>Loading findings…</p>";
  try {
    const { html } = await fetchJSON("/api/findings");
    panel.innerHTML = `<div class="findings-content">${html}</div>`;
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load findings: ${escapeHtml(err.message)}</p>`;
  }
}

async function renderResults(panel) {
  panel.innerHTML = "<p>Loading results…</p>";
  try {
    const { batches } = await fetchJSON("/api/results");
    if (batches.length === 0) {
      panel.innerHTML = `<p class="test-desc">No runs yet — go run a test from the Tests page.</p>`;
      return;
    }
    panel.innerHTML = `
      <div class="filter-field">
        <input type="text" id="results-filter" class="filter-input" placeholder="Search results…" aria-label="Search results">
      </div>
      <table class="results-table">
        <thead><tr><th>Run</th><th>Test</th><th>Runs</th><th>Pass rate</th><th>Duration</th><th>Started</th><th>Artifacts</th></tr></thead>
        <tbody>${batches.map(renderResultRow).join("")}</tbody>
      </table>
      <p id="results-filter-empty" class="test-desc" hidden>No results match.</p>`;
    attachResultsFilter();
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load results: ${escapeHtml(err.message)}</p>`;
  }
}

// Client-side filter for the Results tab — matches nodeid/test name,
// run code, and iteration outcomes (so "RUN-42" finds that run and "fail"
// finds runs with a failed/errored iteration), case-insensitive substring.
// Toggles [hidden] on non-matching <tr>s rather than re-rendering the table.
function attachResultsFilter() {
  const input = document.getElementById("results-filter");
  const emptyMsg = document.getElementById("results-filter-empty");
  if (!input) return;
  const rows = document.querySelectorAll(".results-table tbody tr");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    let anyVisible = false;
    rows.forEach((row) => {
      const haystack = `${row.dataset.nodeid || ""} ${row.dataset.runCode || ""} ${row.dataset.outcomes || ""}`.toLowerCase();
      const match = !q || haystack.includes(q);
      row.hidden = !match;
      if (match) anyVisible = true;
    });
    emptyMsg.hidden = anyVisible;
  });
}

function formatTimestamp(ts) {
  return ts ? ts.replace("T", " ").replace("Z", " UTC") : "—";
}

function renderResultRow(batch) {
  const dots = batch.iterations
    .map(
      (i) =>
        `<span class="iteration-dot ${i.outcome === "pass" ? "pass" : i.outcome === "error" ? "error" : "fail"}"></span>`
    )
    .join("");
  const links =
    batch.iterations
      .flatMap((i) => [
        i.screenshot ? `<a href="/results/${i.screenshot}" target="_blank">screenshot</a>` : null,
        i.trace ? `<a href="/results/${i.trace}" target="_blank">trace</a>` : null,
      ])
      .filter(Boolean)
      .join(" · ") || "—";
  // Older history predates run codes (before the backfill) — those rows
  // just show a plain dash instead of a link, same as elsewhere in this
  // file that surfaces run_code.
  const runCell = batch.run_code
    ? `<a href="#run/${encodeURIComponent(batch.run_code)}">${escapeHtml(batch.run_code)}</a>`
    : `<span class="muted-cell">—</span>`;
  const outcomes = batch.iterations.map((i) => i.outcome).join(" ");
  return `
    <tr data-nodeid="${escapeAttr(batch.nodeid)}" data-run-code="${escapeAttr(batch.run_code || "")}" data-outcomes="${escapeAttr(outcomes)}">
      <td>${runCell}</td>
      <td>${batch.nodeid.split("::").pop()}</td>
      <td><span class="iteration-dots">${dots}</span></td>
      <td>${batch.pass_count}/${batch.total}</td>
      <td>${batch.total_duration.toFixed(1)}s</td>
      <td>${formatTimestamp(batch.started_at)}</td>
      <td>${links}</td>
    </tr>`;
}

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
  } else {
    loadModules();
  }
}

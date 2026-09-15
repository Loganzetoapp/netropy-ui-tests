const state = { catalog: null, liveStatus: {}, batchRunning: false };

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
  try {
    const { groups } = await fetchJSON("/api/catalog");
    state.catalog = groups;
    panel.innerHTML = groups.map(renderGroup).join("");
    attachTestRowHandlers();
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load tests: ${escapeHtml(err.message)}</p>`;
  }
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
      <div>
        <div class="test-name">${test.name}</div>
        <div class="test-desc">${file.short_description}</div>
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
      if (e.target.closest(".run-btn")) return;
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
  // A batch may already be running (e.g. the user switched tabs and back
  // mid-run) — newly attached buttons need to reflect that immediately.
  setRunControlsEnabled(!state.batchRunning);
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

// modalMode distinguishes the two things this one modal now confirms:
// "single" (openRunModal — repeat-count field, calls startRun) and
// "group" (openRunAllModal — no repeat count, calls runAllInGroup).
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

async function runAllInGroup(nodeids, headed = false) {
  for (const nodeid of nodeids) {
    const started = await startRun(nodeid, 1, headed);
    if (!started) {
      // startRun already alerted with the specific reason (e.g. a 409
      // from another batch running). Without this, the loop would go on
      // to await a state.liveStatus[nodeid] === "done" that streamRun
      // never got the chance to set, polling forever on a leaked
      // interval. Stop the sequence here instead of hanging silently.
      alert(`Run all stopped before finishing — "${nodeid}" could not be started.`);
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

document.getElementById("nav-tests").addEventListener("click", () => showPage("tests"));
document.getElementById("nav-results").addEventListener("click", () => showPage("results"));
document.getElementById("nav-findings").addEventListener("click", () => showPage("findings"));
// Overview is the one page-nav tab that's also address-bar-linkable (see
// the routing block near the bottom of this file). Setting the hash (when
// it actually changes) lets the hashchange listener drive the render, so
// clicking here behaves identically to landing directly on #overview;
// when the hash is already "#overview" (no change → no hashchange event
// would fire) render directly instead.
document.getElementById("nav-overview").addEventListener("click", () => {
  if (location.hash === "#overview") {
    showPage("overview");
  } else {
    location.hash = "overview";
  }
});

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

async function renderOverview(panel) {
  panel.innerHTML = "<p>Loading overview…</p>";
  try {
    const { areas } = await fetchJSON("/api/overview");
    panel.innerHTML = `<div class="overview-grid">${areas.map(renderAreaCard).join("")}</div>`;
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load overview: ${escapeHtml(err.message)}</p>`;
  }
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
  const issueHtml =
    area.confirmed_issue_count > 0
      ? `<div class="area-card-row">
           <button type="button" class="pill pill-warn" data-jump="findings">
             ${area.confirmed_issue_count} confirmed issue${area.confirmed_issue_count === 1 ? "" : "s"}
           </button>
         </div>`
      : "";
  return `
    <div class="card area-card">
      <div class="area-card-header">
        <h3>${escapeHtml(area.label)}</h3>
        ${passRatePill}
      </div>
      <div class="area-card-row"><span class="area-card-label">Last run</span> ${lastRunHtml}</div>
      ${flakyHtml}
      ${issueHtml}
    </div>`;
}

// Clicking a confirmed-issue badge (Overview) or the "possible known
// issues" callout's findings link (run-detail) both just want to land on
// the Findings tab — no in-page scrolling. One delegated listener covers
// both regardless of how many times those panels get re-rendered.
document.addEventListener("click", (e) => {
  const btn = e.target.closest('[data-jump="findings"]');
  if (btn) {
    e.preventDefault();
    showPage("findings");
  }
});

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
    ? `<a href="#overview">${escapeHtml(test.area.label)}</a>`
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
      <table class="results-table">
        <thead><tr><th>Run</th><th>Test</th><th>Runs</th><th>Pass rate</th><th>Duration</th><th>Started</th><th>Artifacts</th></tr></thead>
        <tbody>${batches.map(renderResultRow).join("")}</tbody>
      </table>`;
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load results: ${escapeHtml(err.message)}</p>`;
  }
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
  return `
    <tr>
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
  } else {
    loadModules();
  }
}

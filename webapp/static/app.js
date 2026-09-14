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
  if (modalMode === "group") {
    const nodeids = modalGroupNodeids;
    closeRunModal();
    await runAllInGroup(nodeids, headed);
    return;
  }
  const raw = parseInt(document.getElementById("run-modal-count").value, 10);
  const count = Number.isFinite(raw) && raw > 0 ? raw : 1;
  const nodeid = modalNodeid;
  closeRunModal();
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
  state.liveStatus[nodeid] = "running";
  state.batchRunning = true;
  setRunControlsEnabled(false);
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
      if (el) {
        el.textContent = `${payload.status} (${payload.iteration}/${payload.total})`;
        el.className = "pill " + statusPillClass(payload.status);
      }
    } else if (payload.type === "batch_complete") {
      state.liveStatus[nodeid] = "done";
      if (el) el.textContent = `${payload.passed}/${payload.total} passed`;
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

function showPage(page) {
  document.getElementById("nav-tests").classList.toggle("active", page === "tests");
  document.getElementById("nav-results").classList.toggle("active", page === "results");
  document.getElementById("nav-findings").classList.toggle("active", page === "findings");
  const tabs = document.getElementById("module-tabs");
  const panel = document.getElementById("module-panel");
  if (page === "results") {
    tabs.hidden = true;
    renderResults(panel);
  } else if (page === "findings") {
    tabs.hidden = true;
    renderFindings(panel);
  } else {
    tabs.hidden = false;
    loadModules();
  }
}

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
        <thead><tr><th>Test</th><th>Runs</th><th>Pass rate</th><th>Duration</th><th>Started</th><th>Artifacts</th></tr></thead>
        <tbody>${batches.map(renderResultRow).join("")}</tbody>
      </table>`;
  } catch (err) {
    panel.innerHTML = `<p class="test-desc">Couldn't load results: ${escapeHtml(err.message)}</p>`;
  }
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
  return `
    <tr>
      <td>${batch.nodeid.split("::").pop()}</td>
      <td><span class="iteration-dots">${dots}</span></td>
      <td>${batch.pass_count}/${batch.total}</td>
      <td>${batch.total_duration.toFixed(1)}s</td>
      <td>${batch.started_at.replace("T", " ").replace("Z", " UTC")}</td>
      <td>${links}</td>
    </tr>`;
}

loadModules();

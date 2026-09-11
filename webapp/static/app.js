const state = { catalog: null, liveStatus: {} };

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
  const { groups } = await fetchJSON("/api/catalog");
  state.catalog = groups;
  panel.innerHTML = groups.map(renderGroup).join("");
  attachTestRowHandlers();
}

function renderGroup(group) {
  const rows = group.files
    .flatMap((f) => f.tests.map((t) => renderTestRow(t, f)))
    .join("");
  return `
    <section class="group" data-group-id="${group.id}">
      <div class="group-header">
        <h2>${group.label}</h2>
        <button type="button" class="btn-outline run-all-btn" data-nodeids='${JSON.stringify(group.run_all_nodeids)}'>
          Run all in ${group.label.split(" — ")[0]}
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
      openRunModal(btn.dataset.nodeid, btn.dataset.marker);
    });
  });
  document.querySelectorAll(".run-all-btn").forEach((btn) => {
    btn.addEventListener("click", () => runAllInGroup(JSON.parse(btn.dataset.nodeids)));
  });
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

document.getElementById("nav-tests").addEventListener("click", () => showPage("tests"));
document.getElementById("nav-results").addEventListener("click", () => showPage("results"));

function showPage(page) {
  document.getElementById("nav-tests").classList.toggle("active", page === "tests");
  document.getElementById("nav-results").classList.toggle("active", page === "results");
  const tabs = document.getElementById("module-tabs");
  if (page === "results") {
    tabs.hidden = true;
    document.getElementById("module-panel").innerHTML = "<p>Results page — Task 12.</p>";
  } else {
    tabs.hidden = false;
    loadModules();
  }
}

loadModules();

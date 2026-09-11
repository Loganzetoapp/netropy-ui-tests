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
  // Task 10 fills this in.
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

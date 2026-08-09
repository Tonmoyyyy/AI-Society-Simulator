(function () {
  AsimNav.render("citizens");
  AsimSocket.init();

  const PAGE_SIZE = 12;
  let currentPage = 1;

  const TRAIT_ORDER = ["kindness", "intelligence", "ambition", "social", "honesty"];

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function activityClass(activity) {
    if (activity === "idle") return "idle";
    if (activity === "working") return "working";
    return "";
  }

  function citizenCard(c) {
    const traits = TRAIT_ORDER.map(
      (t) => `
        <div class="d-flex align-items-center gap-2 mb-1">
          <span class="text-ink-faint" style="font-size:0.68rem; width:70px; text-transform:uppercase; letter-spacing:0.03em;">${t}</span>
          <div class="trait-bar flex-grow-1">
            <div class="trait-bar-fill" style="width:${c.personality_json[t]}%"></div>
          </div>
        </div>`
    ).join("");

    return `
      <div class="col-sm-6 col-lg-4">
        <div class="citizen-card h-100">
          <div class="d-flex justify-content-between align-items-start mb-1">
            <div class="citizen-name">${escapeHtml(c.name)}</div>
            <span class="badge-activity ${activityClass(c.current_activity)}">${escapeHtml(c.current_activity)}</span>
          </div>
          <div class="citizen-meta mb-2">Age ${c.age} · ${escapeHtml(c.job)}</div>
          <div class="d-flex gap-3 small text-ink-soft mb-2 mono" style="font-size:0.76rem;">
            <span title="Happiness">😊 ${Math.round(c.happiness)}</span>
            <span title="Energy">⚡ ${Math.round(c.energy)}</span>
            <span title="Health">❤ ${Math.round(c.health)}</span>
          </div>
          ${traits}
        </div>
      </div>`;
  }

  function showFeedback(message, isError) {
    const box = document.getElementById("citizens-feedback");
    box.innerHTML = `<div class="${isError ? "alert-asim-error" : "alert alert-light border"}" style="font-size:0.88rem;">${escapeHtml(message)}</div>`;
    setTimeout(() => (box.innerHTML = ""), 4000);
  }

  function renderPagination(total) {
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const nav = document.getElementById("citizens-pagination");
    if (totalPages <= 1) {
      nav.innerHTML = "";
      return;
    }
    let html = '<ul class="pagination">';
    for (let p = 1; p <= totalPages; p++) {
      html += `<li class="page-item${p === currentPage ? " active" : ""}">
        <button class="page-link" data-page="${p}">${p}</button>
      </li>`;
    }
    html += "</ul>";
    nav.innerHTML = html;
    nav.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        currentPage = parseInt(btn.dataset.page, 10);
        loadCitizens();
      });
    });
  }

  async function loadCitizens() {
    const grid = document.getElementById("citizens-grid");
    try {
      const result = await CitizensApi.list(currentPage, PAGE_SIZE);
      document.getElementById("citizen-count-sub").textContent =
        `${result.total} citizen${result.total === 1 ? "" : "s"} in the simulation (v0.1 cap: 100)`;

      if (!result.items.length) {
        grid.innerHTML = `<div class="col-12"><div class="empty-state">No citizens yet. Add the first one to start the simulation.</div></div>`;
      } else {
        grid.innerHTML = result.items.map(citizenCard).join("");
      }
      renderPagination(result.total);
    } catch (err) {
      grid.innerHTML = `<div class="col-12"><div class="alert-asim-error">${escapeHtml(err.message)}</div></div>`;
    }
  }

  document.getElementById("create-citizen-btn").addEventListener("click", async () => {
    if (!Auth.isLoggedIn()) {
      window.location.href = "login.html";
      return;
    }
    const btn = document.getElementById("create-citizen-btn");
    btn.disabled = true;
    try {
      const citizen = await CitizensApi.create();
      showFeedback(`${citizen.name} joined the simulation.`, false);
      currentPage = 1;
      await loadCitizens();
    } catch (err) {
      showFeedback(err.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  loadCitizens();
})();

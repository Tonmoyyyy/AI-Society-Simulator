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
        <div class="citizen-card h-100" data-citizen-id="${c.id}" data-citizen-name="${escapeHtml(c.name)}">
          <div class="d-flex justify-content-between align-items-start mb-1">
            <div class="citizen-name">${escapeHtml(c.name)}</div>
            <span class="badge-activity ${activityClass(c.current_activity)}">${escapeHtml(c.current_activity)}</span>
          </div>
          <div class="citizen-meta mb-2">Age ${c.age} · ${escapeHtml(c.job)} · ${escapeHtml(c.neighborhood || "")}</div>
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
        grid.querySelectorAll(".citizen-card").forEach((card) => {
          card.style.cursor = "pointer";
          card.addEventListener("click", () => {
            window.location.href = `citizen.html?id=${card.dataset.citizenId}`;
          });
        });
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

  // ---- Customize & add modal ----

  async function populateCustomizeOptions() {
    const jobSelect = document.getElementById("cust-job");
    const neighborhoodSelect = document.getElementById("cust-neighborhood");
    try {
      const options = await CitizensApi.options();
      (options.jobs || []).forEach((job) => {
        const opt = document.createElement("option");
        opt.value = job;
        opt.textContent = job;
        jobSelect.appendChild(opt);
      });
      (options.neighborhoods || []).forEach((n) => {
        const opt = document.createElement("option");
        opt.value = n;
        opt.textContent = n;
        neighborhoodSelect.appendChild(opt);
      });
    } catch (_) {
      // non-fatal — "Random" is still selectable, form still usable
    }
  }

  const TRAIT_LABELS = {
    kindness: "Kindness", intelligence: "Intelligence", ambition: "Ambition",
    social: "Social", honesty: "Honesty",
  };

  function renderPersonalitySliders() {
    const container = document.getElementById("cust-traits");
    container.innerHTML = TRAIT_ORDER.map(
      (t) => `
      <div class="mb-2">
        <div class="d-flex justify-content-between">
          <label class="small text-ink-soft" for="cust-trait-${t}">${TRAIT_LABELS[t]}</label>
          <span class="small mono" id="cust-trait-${t}-val">50</span>
        </div>
        <input type="range" class="form-range" id="cust-trait-${t}" min="0" max="100" value="50" />
      </div>`
    ).join("");
    TRAIT_ORDER.forEach((t) => {
      const slider = document.getElementById(`cust-trait-${t}`);
      const val = document.getElementById(`cust-trait-${t}-val`);
      slider.addEventListener("input", () => (val.textContent = slider.value));
    });
  }

  document.getElementById("cust-personality-toggle").addEventListener("change", (e) => {
    const box = document.getElementById("cust-personality-sliders");
    box.classList.toggle("d-none", !e.target.checked);
    if (e.target.checked && !box.dataset.rendered) {
      renderPersonalitySliders();
      box.dataset.rendered = "1";
    }
  });

  document.getElementById("customize-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!Auth.isLoggedIn()) {
      window.location.href = "login.html";
      return;
    }
    const errorBox = document.getElementById("customize-error");
    errorBox.classList.add("d-none");

    const fields = {};
    const name = document.getElementById("cust-name").value.trim();
    const age = document.getElementById("cust-age").value;
    const job = document.getElementById("cust-job").value;
    const neighborhood = document.getElementById("cust-neighborhood").value;
    if (name) fields.name = name;
    if (age) fields.age = parseInt(age, 10);
    if (job) fields.job = job;
    if (neighborhood) fields.neighborhood = neighborhood;

    if (document.getElementById("cust-personality-toggle").checked) {
      fields.personality_json = {};
      TRAIT_ORDER.forEach((t) => {
        fields.personality_json[t] = parseInt(document.getElementById(`cust-trait-${t}`).value, 10);
      });
    }

    try {
      const citizen = await CitizensApi.create(fields);
      showFeedback(`${citizen.name} joined the simulation.`, false);
      bootstrap.Modal.getInstance(document.getElementById("customize-modal")).hide();
      document.getElementById("customize-form").reset();
      currentPage = 1;
      await loadCitizens();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove("d-none");
    }
  });

  populateCustomizeOptions();
  loadCitizens();
})();

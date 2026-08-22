/**
 * The citizens roster.
 *
 * FILTERING IS SERVER SIDE. `include_dead`, `gender` and `search` are all query
 * parameters on GET /api/v1/citizens, so `total` counts the same filtered set as
 * `items` and the pagination underneath stays correct. Filtering a fetched page
 * client-side would have shown "page 3 of 9" over four results.
 *
 * DECEASED CITIZENS ARE HIDDEN BY DEFAULT and reachable with one checkbox. That
 * default is what keeps this page a population rather than a cemetery; the
 * checkbox is what makes a death that was recorded by mistake findable, and from
 * the profile page, undoable.
 */
(function () {
  AsimNav.render("citizens");
  AsimSocket.init();

  const PAGE_SIZE = 12;
  const SEARCH_DEBOUNCE_MS = 300;

  let currentPage = 1;
  let searchTimer = null;

  const TRAIT_ORDER = ["kindness", "intelligence", "ambition", "social", "honesty"];

  // Stored value -> display label, filled from GET /api/v1/citizens/options so
  // this page never keeps its own copy of the gender vocabulary.
  const genderLabels = {};

  // ATTRIBUTE-SAFE. The obvious one-liner (set textContent, read innerHTML)
  // escapes &, < and > but leaves quotes alone, and this helper's output goes
  // into `data-citizen-name="..."` below. A citizen called `" onmouseover="…`
  // would break out of that attribute — and names are user-supplied through
  // POST /api/v1/citizens with no character filtering, on a page any visitor can
  // open. So the quotes are escaped explicitly.
  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function activityClass(activity) {
    if (activity === "idle") return "idle";
    if (activity === "working") return "working";
    return "";
  }

  function genderLabel(value) {
    return genderLabels[value] || value || "unknown";
  }

  function currentFilters() {
    return {
      search: document.getElementById("filter-search").value.trim(),
      gender: document.getElementById("filter-gender").value,
      includeDead: document.getElementById("filter-include-dead").checked,
    };
  }

  function anyFilterActive(f) {
    return !!(f.search || f.gender || f.includeDead);
  }

  // ------------------------------------------------------------ citizen cards

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

    // A dead citizen keeps their card — a death is recorded, not erased — but the
    // avatar desaturates and the activity badge is replaced by the fact of the
    // death. Slate, not red: see the note in custom.css.
    const badge = c.is_alive
      ? `<span class="badge-activity ${activityClass(c.current_activity)}">${escapeHtml(c.current_activity)}</span>`
      : `<span class="badge-activity idle">deceased</span>`;

    return `
      <div class="col-sm-6 col-lg-4">
        <div class="citizen-card h-100${c.is_alive ? "" : " is-deceased"}" data-citizen-id="${c.id}" data-citizen-name="${escapeHtml(c.name)}">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div class="d-flex align-items-center gap-2">
              ${AsimAvatar.ringedImg(c.id, c.current_activity, 44)}
              <div>
                <div class="citizen-name">${escapeHtml(c.name)}</div>
                ${
                  c.national_id
                    ? `<div class="text-ink-faint mono" style="font-size:0.68rem;">${escapeHtml(c.national_id)}</div>`
                    : ""
                }
              </div>
            </div>
            ${badge}
          </div>
          <div class="citizen-meta mb-2">Age ${c.age} · ${escapeHtml(genderLabel(c.gender))} · ${escapeHtml(c.job)} · ${escapeHtml(c.neighborhood || "")}</div>
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
    const filters = currentFilters();
    try {
      const result = await CitizensApi.list(currentPage, PAGE_SIZE, filters);

      document.getElementById("citizen-count-sub").textContent = anyFilterActive(filters)
        ? `${result.total} match${result.total === 1 ? "" : "es"} for the current filters`
        : `${result.total} living citizen${result.total === 1 ? "" : "s"} in the simulation`;

      if (!result.items.length) {
        grid.innerHTML = `<div class="col-12"><div class="empty-state">${
          anyFilterActive(filters)
            ? "Nobody matches those filters."
            : "No citizens yet. Add the first one to start the simulation."
        }</div></div>`;
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

  // ------------------------------------------------------------ demographics

  function statTile(label, value, sub) {
    return `
      <div class="col-6 col-md-3 col-lg-2">
        <div class="stat-label">${escapeHtml(label)}</div>
        <div class="stat-value" style="font-size:1.5rem;">${escapeHtml(String(value))}</div>
        ${sub ? `<div class="stat-sub">${escapeHtml(sub)}</div>` : ""}
      </div>`;
  }

  async function loadDemographics() {
    const strip = document.getElementById("demo-strip");
    try {
      const demo = await CitizensApi.demographics();

      // Gender tiles come from the payload's own breakdown — including the zeros,
      // which the backend fills in deliberately so a legend doesn't reorder
      // itself between refreshes. Nothing here names a gender.
      const genderTiles = (demo.gender_breakdown || [])
        .map((g) => {
          genderLabels[g.gender] = g.label;
          const share = demo.living ? Math.round((g.count / demo.living) * 100) : 0;
          return statTile(g.label, g.count, `${share}% of the living`);
        })
        .join("");

      strip.innerHTML =
        statTile("Living", demo.living) +
        statTile("Deceased", demo.deceased, `${demo.total_ever} ever lived`) +
        genderTiles;

      document.getElementById("demo-avg-age").textContent =
        demo.average_age == null
          ? "no one to average yet"
          : `average age ${demo.average_age}`;
    } catch (err) {
      strip.innerHTML = `<div class="col-12"><div class="text-ink-faint small">Couldn't load population figures: ${escapeHtml(err.message)}</div></div>`;
    }
  }

  // --------------------------------------------------------------- filtering

  function onFilterChanged() {
    currentPage = 1; // page 4 of the old result set may not exist in the new one
    loadCitizens();
  }

  document.getElementById("filter-search").addEventListener("input", () => {
    // Debounced: this is a server round trip per keystroke otherwise.
    clearTimeout(searchTimer);
    searchTimer = setTimeout(onFilterChanged, SEARCH_DEBOUNCE_MS);
  });
  document.getElementById("filter-gender").addEventListener("change", onFilterChanged);
  document.getElementById("filter-include-dead").addEventListener("change", onFilterChanged);

  // ------------------------------------------------------------ create citizen

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
      await Promise.all([loadCitizens(), loadDemographics()]);
    } catch (err) {
      showFeedback(err.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  // ---- Customize & add modal ----

  async function populateOptions() {
    const jobSelect = document.getElementById("cust-job");
    const neighborhoodSelect = document.getElementById("cust-neighborhood");
    const custGender = document.getElementById("cust-gender");
    const filterGender = document.getElementById("filter-gender");
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
      // One source, two selects: the create form's "Gender" and the roster's
      // "Gender" filter. Both keep their own leading "Random"/"Any" option.
      (options.genders || []).forEach((g) => {
        genderLabels[g.value] = g.label;
        [custGender, filterGender].forEach((select) => {
          const opt = document.createElement("option");
          opt.value = g.value;
          opt.textContent = g.label;
          select.appendChild(opt);
        });
      });
    } catch (_) {
      // non-fatal — "Random"/"Any" are still selectable, both forms still work
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

    // Only non-empty fields are sent. Every omitted field is randomized server
    // side, which is why "Random" is the empty value rather than a magic string.
    const fields = {};
    const name = document.getElementById("cust-name").value.trim();
    const age = document.getElementById("cust-age").value;
    const gender = document.getElementById("cust-gender").value;
    const nationalId = document.getElementById("cust-national-id").value.trim();
    const job = document.getElementById("cust-job").value;
    const neighborhood = document.getElementById("cust-neighborhood").value;
    if (name) fields.name = name;
    if (age) fields.age = parseInt(age, 10);
    if (gender) fields.gender = gender;
    if (nationalId) fields.national_id = nationalId.toUpperCase();
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
      await Promise.all([loadCitizens(), loadDemographics()]);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove("d-none");
    }
  });

  // A death or a deletion changes the counts, so refresh the strip too. The
  // profile page sends us back here with ?deleted=1 after a hard delete.
  if (new URLSearchParams(window.location.search).get("deleted") === "1") {
    showFeedback("Citizen record deleted.", false);
    // Cleaned out of the URL so a refresh doesn't repeat the message.
    window.history.replaceState({}, "", window.location.pathname);
  }

  document.addEventListener("asim:ws-message", (e) => {
    if (e.detail && e.detail.type === "citizen_died") {
      loadDemographics();
      loadCitizens();
    }
  });

  populateOptions().then(() => {
    loadCitizens();
    loadDemographics();
  });
})();

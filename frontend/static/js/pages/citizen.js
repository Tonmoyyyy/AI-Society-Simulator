/**
 * One citizen — profile, wallet, memories, and the admin editor.
 *
 * WHAT CHANGED HERE AND WHY
 * -------------------------
 * This page used to be read-only apart from a job dropdown and a money
 * transfer. It is now the place where a citizen is customized end to end: name,
 * National ID, gender, age, job, neighborhood, personality and wellbeing, plus
 * the two death operations. That is the "sobar id customized korte parbo / dead
 * korte parbo" half of the request.
 *
 * ONLY CHANGED FIELDS ARE SENT. The form is diffed against the citizen as
 * loaded (see buildChangedFields), so PATCH carries just the keys you touched.
 * The backend's `exclude_unset` then leaves everything else alone. This matters
 * because the tick engine is editing the same row while the form sits open — a
 * naive "send the whole form" save would quietly roll happiness and energy back
 * to whatever they were when the page loaded.
 *
 * A DEATH IS NOT A DELETE. `recordDeath` keeps the row, the wallet, the posts,
 * the memories and the timeline, and vacates any office held — which is why the
 * response's `vacated_offices` is surfaced rather than ignored. `remove` is the
 * hard delete, kept visually apart in the danger zone.
 *
 * NOTHING IS HARDCODED. Jobs, neighborhoods and the gender vocabulary all come
 * from GET /api/v1/citizens/options, so adding a job backend-side adds it here
 * with no edit.
 */
(function () {
  AsimNav.render("citizens");
  AsimSocket.init();

  const TRAIT_ORDER = ["kindness", "intelligence", "ambition", "social", "honesty"];
  const TRAIT_LABELS = {
    kindness: "Kindness",
    intelligence: "Intelligence",
    ambition: "Ambition",
    social: "Social",
    honesty: "Honesty",
  };
  // label, element id suffix, min, max, step
  const WELLBEING_FIELDS = [
    { key: "happiness", label: "Happiness", min: 0, max: 100, step: 1 },
    { key: "energy", label: "Energy", min: 0, max: 100, step: 1 },
    { key: "health", label: "Health", min: 0, max: 100, step: 1 },
    { key: "mood", label: "Mood", min: -1, max: 1, step: 0.05 },
  ];

  const params = new URLSearchParams(window.location.search);
  const citizenId = params.get("id");

  // The citizen exactly as the server last returned them — what the read-only
  // panels, the confirm dialogs and every request id come from.
  let citizen = null;
  // The snapshot the FORM was seeded from, which is a different thing. Diffing
  // against this rather than against `citizen` is what lets a tick land while the
  // form is open: the tick moves `citizen.happiness`, the form still holds the
  // value it was seeded with, they agree, and happiness is left out of the PATCH
  // instead of being silently rolled back to what it was when the page loaded.
  let formBase = null;
  let formDirty = false;
  const genderLabels = {};

  // ATTRIBUTE-SAFE — the same explicit chain used on the citizens roster and the
  // government console. The textContent/innerHTML one-liner this file used
  // before escapes & < > but leaves quotes alone, and names here are
  // user-supplied with no character filtering. Cheap enough to just always do
  // the safe thing rather than audit every call site.
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

  function moneyFormat(value) {
    return "$" + Number(value).toFixed(2);
  }

  function genderLabel(value) {
    return genderLabels[value] || value || "unknown";
  }

  // Mood is a -1..1 float on the wire but a stepped slider in the form, and a
  // browser SNAPS a range input to the nearest step. Without rounding the stored
  // value the same way, a citizen sitting at mood 0.13 would read as edited the
  // moment the form opened (slider shows 0.15) and every save would carry a mood
  // change nobody asked for. Ties round up, matching the HTML spec.
  const MOOD_STEP = 0.05;
  function toMoodStep(value) {
    return Number((Math.round(Number(value) / MOOD_STEP) * MOOD_STEP).toFixed(2));
  }

  function feedback(boxId, message, isError) {
    const box = document.getElementById(boxId);
    box.innerHTML = `<div class="${
      isError ? "alert-asim-error" : "alert alert-light border"
    }" style="font-size:0.82rem; padding:0.4rem 0.6rem;">${escapeHtml(message)}</div>`;
    // Errors stay put; confirmations clear themselves so the page doesn't
    // accumulate stale "saved" messages.
    if (!isError) setTimeout(() => (box.innerHTML = ""), 5000);
  }

  const showManageFeedback = (m, e) => feedback("manage-feedback", m, e);
  const showEditorFeedback = (m, e) => feedback("editor-feedback", m, e);
  const showDangerFeedback = (m, e) => feedback("danger-feedback", m, e);

  // ------------------------------------------------------------ read-only view

  function renderTraits(personality) {
    return TRAIT_ORDER.map(
      (t) => `
        <div class="d-flex align-items-center gap-2 mb-2">
          <span class="text-ink-faint" style="font-size:0.72rem; width:80px; text-transform:uppercase; letter-spacing:0.03em;">${t}</span>
          <div class="trait-bar flex-grow-1">
            <div class="trait-bar-fill" style="width:${personality[t]}%"></div>
          </div>
          <span class="mono text-ink-faint" style="font-size:0.72rem; width:28px; text-align:right;">${personality[t]}</span>
        </div>`
    ).join("");
  }

  function renderPurchases(purchases) {
    if (!purchases.length) {
      return '<div class="text-ink-faint small">No purchases yet.</div>';
    }
    return purchases
      .map(
        (p) => `
        <div class="d-flex justify-content-between py-1 border-bottom small">
          <span>${escapeHtml(p.product_name)} <span class="text-ink-faint">· ${escapeHtml(p.shop_name)}</span></span>
          <span class="mono">${moneyFormat(p.price)}</span>
        </div>`
      )
      .join("");
  }

  function renderMemories(memories) {
    if (!memories.length) {
      return '<div class="text-ink-faint small">Nothing memorable yet — run a few ticks.</div>';
    }
    return memories
      .map(
        (m) => `
        <div class="mb-2 pb-2 border-bottom">
          <div class="d-flex justify-content-between">
            <span class="badge-activity">${escapeHtml(m.event_type)}</span>
            <span class="text-ink-faint small mono">importance ${m.importance}</span>
          </div>
          <div class="small mt-1">${escapeHtml(m.description)}</div>
        </div>`
      )
      .join("");
  }

  /** The memorial banner, the grayscale treatment and the death/revive swap. */
  function renderLiveness(c) {
    const banner = document.getElementById("memorial-banner");
    const header = document.getElementById("citizen-header-card");
    const deathBlock = document.getElementById("death-block");

    if (c.is_alive) {
      banner.classList.add("d-none");
      header.classList.remove("is-deceased");
      deathBlock.classList.remove("d-none");
      return;
    }

    const when =
      c.died_at_tick == null ? "at an unrecorded tick" : `at tick ${c.died_at_tick}`;
    const why = c.death_cause ? ` · ${c.death_cause}` : "";
    document.getElementById("memorial-detail").textContent =
      `${c.name} died ${when}${why}. Their posts, purchases and memories are kept.`;
    banner.classList.remove("d-none");
    header.classList.add("is-deceased");
    // Nothing to record — they are already dead. Revive lives in the banner.
    deathBlock.classList.add("d-none");
  }

  // ----------------------------------------------------------- editor controls

  function renderTraitSliders() {
    const box = document.getElementById("edit-traits");
    box.innerHTML = TRAIT_ORDER.map(
      (t) => `
      <div class="mb-2">
        <div class="d-flex justify-content-between">
          <label class="small text-ink-soft" for="edit-trait-${t}">${TRAIT_LABELS[t]}</label>
          <span class="small mono" id="edit-trait-${t}-val">—</span>
        </div>
        <input type="range" class="form-range" id="edit-trait-${t}" min="0" max="100" step="1" />
      </div>`
    ).join("");
    TRAIT_ORDER.forEach((t) => bindSliderReadout(`edit-trait-${t}`, 0));
  }

  function renderWellbeingSliders() {
    const box = document.getElementById("edit-wellbeing");
    box.innerHTML = WELLBEING_FIELDS.map(
      (f) => `
      <div class="mb-2">
        <div class="d-flex justify-content-between">
          <label class="small text-ink-soft" for="edit-${f.key}">${f.label}</label>
          <span class="small mono" id="edit-${f.key}-val">—</span>
        </div>
        <input type="range" class="form-range" id="edit-${f.key}"
               min="${f.min}" max="${f.max}" step="${f.step}" />
      </div>`
    ).join("");
    WELLBEING_FIELDS.forEach((f) =>
      bindSliderReadout(`edit-${f.key}`, f.step < 1 ? 2 : 0)
    );
  }

  /** Keeps the number next to a slider in step with its thumb. */
  function bindSliderReadout(id, decimals) {
    const slider = document.getElementById(id);
    const out = document.getElementById(`${id}-val`);
    const sync = () => (out.textContent = Number(slider.value).toFixed(decimals));
    slider.addEventListener("input", sync);
    slider.dataset.decimals = String(decimals);
  }

  function syncAllReadouts() {
    TRAIT_ORDER.forEach((t) => syncReadout(`edit-trait-${t}`));
    WELLBEING_FIELDS.forEach((f) => syncReadout(`edit-${f.key}`));
  }

  function syncReadout(id) {
    const slider = document.getElementById(id);
    const out = document.getElementById(`${id}-val`);
    out.textContent = Number(slider.value).toFixed(Number(slider.dataset.decimals || 0));
  }

  /** Adds `value` to a <select> if the backend's option list doesn't contain it.
   *  A citizen created before a job was renamed still has the old string, and a
   *  select that silently dropped it would show the wrong job as if it were
   *  current — and then save that wrong job. */
  function ensureOption(select, value, label) {
    if (value == null || value === "") return;
    const exists = Array.from(select.options).some((o) => o.value === value);
    if (exists) return;
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label || `${value} (not in the current list)`;
    select.appendChild(opt);
  }

  async function populateOptions() {
    const jobSelect = document.getElementById("edit-job");
    const neighborhoodSelect = document.getElementById("edit-neighborhood");
    const genderSelect = document.getElementById("edit-gender");
    try {
      const options = await CitizensApi.options();
      (options.jobs || []).forEach((job) => {
        if (job === "unemployed") return; // already the markup default
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
      (options.genders || []).forEach((g) => {
        genderLabels[g.value] = g.label;
        const opt = document.createElement("option");
        opt.value = g.value;
        opt.textContent = g.label;
        genderSelect.appendChild(opt);
      });
    } catch (_) {
      // Non-fatal. The form still saves the fields whose <select> did populate,
      // and ensureOption below keeps the citizen's own values selectable.
    }
  }

  function fillForm(c) {
    document.getElementById("edit-name").value = c.name || "";
    document.getElementById("edit-national-id").value = c.national_id || "";
    document.getElementById("edit-age").value = c.age;
    document.getElementById("edit-activity").value = c.current_activity || "";

    const jobSelect = document.getElementById("edit-job");
    const neighborhoodSelect = document.getElementById("edit-neighborhood");
    const genderSelect = document.getElementById("edit-gender");
    ensureOption(jobSelect, c.job);
    ensureOption(neighborhoodSelect, c.neighborhood);
    ensureOption(genderSelect, c.gender, c.gender_label);
    jobSelect.value = c.job || "unemployed";
    neighborhoodSelect.value = c.neighborhood || "";
    genderSelect.value = c.gender || "";

    TRAIT_ORDER.forEach((t) => {
      document.getElementById(`edit-trait-${t}`).value = c.personality_json[t];
    });
    // Rounded to the slider's own resolution so that a citizen sitting at 73.4
    // doesn't read as "changed" the instant the form opens. See snapshotOf.
    document.getElementById("edit-happiness").value = Math.round(c.happiness);
    document.getElementById("edit-energy").value = Math.round(c.energy);
    document.getElementById("edit-health").value = Math.round(c.health);
    document.getElementById("edit-mood").value = toMoodStep(c.mood).toFixed(2);

    syncAllReadouts();
    formBase = snapshotOf(c);
    setDirty(false);
  }

  function setDirty(dirty) {
    formDirty = dirty;
    document.getElementById("editor-dirty-note").textContent = dirty
      ? "Unsaved changes"
      : "";
  }

  /** The citizen's values at the slider/select resolution the form can express.
   *  Diffing form-against-this rather than form-against-raw is what stops
   *  rounding alone from counting as an edit. */
  function snapshotOf(c) {
    return {
      name: c.name || "",
      national_id: c.national_id || "",
      gender: c.gender || "",
      age: c.age,
      job: c.job || "unemployed",
      neighborhood: c.neighborhood || "",
      current_activity: c.current_activity || "",
      happiness: Math.round(c.happiness),
      energy: Math.round(c.energy),
      health: Math.round(c.health),
      mood: toMoodStep(c.mood),
      personality: Object.fromEntries(TRAIT_ORDER.map((t) => [t, c.personality_json[t]])),
    };
  }

  function snapshotOfForm() {
    return {
      name: document.getElementById("edit-name").value.trim(),
      national_id: document.getElementById("edit-national-id").value.trim().toUpperCase(),
      gender: document.getElementById("edit-gender").value,
      age: parseInt(document.getElementById("edit-age").value, 10),
      job: document.getElementById("edit-job").value,
      neighborhood: document.getElementById("edit-neighborhood").value,
      current_activity: document.getElementById("edit-activity").value.trim(),
      happiness: parseInt(document.getElementById("edit-happiness").value, 10),
      energy: parseInt(document.getElementById("edit-energy").value, 10),
      health: parseInt(document.getElementById("edit-health").value, 10),
      mood: Number(parseFloat(document.getElementById("edit-mood").value).toFixed(2)),
      personality: Object.fromEntries(
        TRAIT_ORDER.map((t) => [
          t,
          parseInt(document.getElementById(`edit-trait-${t}`).value, 10),
        ])
      ),
    };
  }

  /**
   * The PATCH body: only what actually differs.
   *
   * Blank text fields mean "leave alone", never "clear". That is not just a UI
   * courtesy — the service drops None values, so `national_id: null` would be a
   * silent no-op and the admin would be told it saved when nothing happened.
   * Better to not offer clearing than to pretend to.
   */
  function buildChangedFields() {
    const base = formBase;
    const now = snapshotOfForm();
    const fields = {};

    ["name", "national_id", "current_activity"].forEach((key) => {
      if (now[key] && now[key] !== base[key]) fields[key] = now[key];
    });
    ["gender", "job", "neighborhood"].forEach((key) => {
      if (now[key] && now[key] !== base[key]) fields[key] = now[key];
    });
    ["age", "happiness", "energy", "health", "mood"].forEach((key) => {
      if (!Number.isNaN(now[key]) && now[key] !== base[key]) fields[key] = now[key];
    });
    if (TRAIT_ORDER.some((t) => now.personality[t] !== base.personality[t])) {
      // All five traits or none — the schema rejects a partial dict.
      fields.personality_json = now.personality;
    }
    return fields;
  }

  // -------------------------------------------------------------------- load

  function showLoadError(message) {
    document.getElementById("citizen-loading").classList.add("d-none");
    const errBox = document.getElementById("citizen-error");
    errBox.textContent = message;
    errBox.classList.remove("d-none");
  }

  async function load() {
    if (!citizenId) {
      showLoadError("No citizen selected — go back and pick one.");
      return;
    }

    try {
      const [fresh, wallet, purchases, memories] = await Promise.all([
        CitizensApi.get(citizenId),
        CitizensApi.wallet(citizenId).catch(() => ({ balance: 0 })),
        CitizensApi.purchases(citizenId, 10).catch(() => []),
        CitizensApi.memories(citizenId, 10).catch(() => []),
      ]);

      const wasDirty = formDirty;
      citizen = fresh;

      document.getElementById("c-name").textContent = fresh.name;
      document.getElementById("c-avatar").innerHTML = AsimAvatar.ringedImg(
        fresh.id,
        fresh.current_activity,
        72
      );
      document.getElementById("c-age").textContent = fresh.age;
      document.getElementById("c-gender").textContent = genderLabel(fresh.gender);
      document.getElementById("c-job").textContent = fresh.job;
      document.getElementById("c-neighborhood").textContent = fresh.neighborhood || "";
      document.getElementById("c-national-id").textContent = fresh.national_id || "none";
      document.getElementById("c-id").textContent = fresh.id;

      const activityEl = document.getElementById("c-activity");
      activityEl.textContent = fresh.current_activity;
      activityEl.className = `badge-activity ${activityClass(fresh.current_activity)}`;

      document.getElementById("c-happiness").textContent = Math.round(fresh.happiness);
      document.getElementById("c-energy").textContent = Math.round(fresh.energy);
      document.getElementById("c-health").textContent = Math.round(fresh.health);
      document.getElementById("c-mood").textContent = Number(fresh.mood).toFixed(2);

      document.getElementById("c-traits").innerHTML = renderTraits(fresh.personality_json);
      document.getElementById("c-balance").textContent = moneyFormat(wallet.balance);
      document.getElementById("c-purchases").innerHTML = renderPurchases(purchases);
      document.getElementById("c-memories").innerHTML = renderMemories(memories);

      renderLiveness(fresh);

      // A tick landing mid-edit must not throw away what the admin typed. The
      // read-only panels above are refreshed either way; the form is only
      // re-seeded when there is nothing to lose.
      if (wasDirty) {
        showEditorFeedback(
          "This citizen changed on the server. Your unsaved edits were kept — press Revert to discard them.",
          false
        );
      } else {
        fillForm(fresh);
      }

      document.getElementById("citizen-loading").classList.add("d-none");
      document.getElementById("citizen-content").classList.remove("d-none");
    } catch (err) {
      showLoadError(err.message);
    }
  }

  // ----------------------------------------------------------------- actions

  document.getElementById("profile-form").addEventListener("input", () => setDirty(true));

  document.getElementById("profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!citizen || !formBase) return;

    const fields = buildChangedFields();
    if (!Object.keys(fields).length) {
      showEditorFeedback("Nothing changed.", false);
      return;
    }

    const btn = document.getElementById("profile-save-btn");
    btn.disabled = true;
    try {
      await CitizensApi.update(citizen.id, fields);
      // Cleared BEFORE reloading, so load() re-seeds the form from what the
      // server actually accepted — a national ID comes back uppercased.
      setDirty(false);
      showEditorFeedback(
        `Saved: ${Object.keys(fields).join(", ").replace("personality_json", "personality")}.`,
        false
      );
      await load();
    } catch (err) {
      showEditorFeedback(err.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("profile-revert-btn").addEventListener("click", () => {
    if (citizen) fillForm(citizen);
  });

  document.getElementById("transfer-btn").addEventListener("click", async () => {
    const toId = document.getElementById("transfer-to-id").value;
    const amount = document.getElementById("transfer-amount").value;
    if (!toId || !amount) {
      showManageFeedback("Enter a citizen ID and an amount.", true);
      return;
    }
    try {
      await CitizensApi.transfer(citizenId, parseInt(toId, 10), parseFloat(amount));
      showManageFeedback(`Sent $${amount} to citizen #${toId}.`, false);
      document.getElementById("transfer-to-id").value = "";
      document.getElementById("transfer-amount").value = "";
      load();
    } catch (err) {
      showManageFeedback(err.message, true);
    }
  });

  document.getElementById("record-death-btn").addEventListener("click", async () => {
    if (!citizen) return;
    const cause = document.getElementById("death-cause").value.trim();
    if (
      !window.confirm(
        `Record ${citizen.name} as deceased?\n\nThey stop counting as population and lose any office, but their posts, purchases and memories are kept. This can be undone.`
      )
    ) {
      return;
    }
    try {
      const result = await CitizensApi.recordDeath(citizen.id, cause || null);
      // Killing the President also empties the presidency. Saying so is the
      // whole reason the endpoint returns this list.
      const vacated = result.vacated_offices || [];
      const note = vacated.length
        ? ` Offices vacated: ${vacated.join(", ")}.`
        : "";
      document.getElementById("death-cause").value = "";
      showDangerFeedback(`${citizen.name} recorded as deceased.${note}`, false);
      await load();
    } catch (err) {
      showDangerFeedback(err.message, true);
    }
  });

  document.getElementById("revive-btn").addEventListener("click", async () => {
    if (!citizen) return;
    if (
      !window.confirm(
        `Bring ${citizen.name} back?\n\nThis undoes the death record. It does NOT restore any office they held — someone else may already sit there.`
      )
    ) {
      return;
    }
    try {
      await CitizensApi.revive(citizen.id);
      // No success message: load() hides the banner, which says it better than
      // any sentence would.
      await load();
    } catch (err) {
      feedback("memorial-feedback", err.message, true);
    }
  });

  document.getElementById("delete-citizen-btn").addEventListener("click", async () => {
    if (!citizen) return;
    // Two prompts, not one, and the second asks for the name. A hard delete
    // cascades through posts, comments, memories and wallet — worth the friction.
    if (
      !window.confirm(
        `Permanently delete ${citizen.name}?\n\nEverything attached to them goes too: wallet, posts, comments, memories. This cannot be undone.\n\nIf they died, use "Record death" instead.`
      )
    ) {
      return;
    }
    const typed = window.prompt(`Type this citizen's name to confirm deletion:`);
    if (typed === null) return;
    if (typed.trim() !== citizen.name) {
      showDangerFeedback("Name didn't match — nothing was deleted.", true);
      return;
    }
    try {
      await CitizensApi.remove(citizen.id);
      window.location.href = "citizens.html?deleted=1";
    } catch (err) {
      showDangerFeedback(err.message, true);
    }
  });

  // ---------------------------------------------------------------- gating
  //
  // The controls are hidden rather than disabled when logged out, because a
  // logged-out visitor has nothing to fix by clicking them. The backend is still
  // the real gate: PATCH needs any account, death/revive need an admin, and a
  // 403 makes apiFetch drop the session and send you to the login page.

  if (!Auth.isLoggedIn()) {
    document.getElementById("manage-login-notice").classList.remove("d-none");
    document.getElementById("manage-controls").classList.add("d-none");
    document.getElementById("editor-login-notice").classList.remove("d-none");
    document.getElementById("editor-body").classList.add("d-none");
    document.getElementById("danger-login-notice").classList.remove("d-none");
    document.getElementById("danger-body").classList.add("d-none");
    // Lives in the memorial banner rather than the danger card, so it needs
    // hiding separately — otherwise it's the one write control a logged-out
    // visitor can still see.
    document.getElementById("revive-btn").classList.add("d-none");
  }

  // Live updates: a tick moved this citizen, or somebody else edited them.
  document.addEventListener("asim:ws-message", (e) => {
    const d = e.detail;
    if (!d) return;
    if (String(d.citizen_id) === String(citizenId)) {
      load();
    }
  });

  renderTraitSliders();
  renderWellbeingSliders();
  populateOptions().then(load);
})();

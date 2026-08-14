(function () {
  AsimNav.render("citizens");
  AsimSocket.init();

  const TRAIT_ORDER = ["kindness", "intelligence", "ambition", "social", "honesty"];

  const params = new URLSearchParams(window.location.search);
  const citizenId = params.get("id");

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

  function moneyFormat(value) {
    return "$" + Number(value).toFixed(2);
  }

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

  async function load() {
    if (!citizenId) {
      document.getElementById("citizen-loading").classList.add("d-none");
      const errBox = document.getElementById("citizen-error");
      errBox.textContent = "No citizen selected — go back and pick one.";
      errBox.classList.remove("d-none");
      return;
    }

    try {
      const [citizen, wallet, purchases, memories] = await Promise.all([
        CitizensApi.get(citizenId),
        CitizensApi.wallet(citizenId).catch(() => ({ balance: 0 })),
        CitizensApi.purchases(citizenId, 10).catch(() => []),
        CitizensApi.memories(citizenId, 10).catch(() => []),
      ]);

      document.getElementById("c-name").textContent = citizen.name;
      document.getElementById("c-avatar").innerHTML = AsimAvatar.ringedImg(citizen.id, citizen.current_activity, 72);
      document.getElementById("c-age").textContent = citizen.age;
      document.getElementById("c-job").textContent = citizen.job;
      document.getElementById("c-neighborhood").textContent = citizen.neighborhood || "";
      document.getElementById("assign-job-select").value = citizen.job;
      const activityEl = document.getElementById("c-activity");
      activityEl.textContent = citizen.current_activity;
      activityEl.className = `badge-activity ${activityClass(citizen.current_activity)}`;

      document.getElementById("c-happiness").textContent = Math.round(citizen.happiness);
      document.getElementById("c-energy").textContent = Math.round(citizen.energy);
      document.getElementById("c-health").textContent = Math.round(citizen.health);
      document.getElementById("c-mood").textContent = citizen.mood.toFixed(2);

      document.getElementById("c-traits").innerHTML = renderTraits(citizen.personality_json);
      document.getElementById("c-balance").textContent = moneyFormat(wallet.balance);
      document.getElementById("c-purchases").innerHTML = renderPurchases(purchases);
      document.getElementById("c-memories").innerHTML = renderMemories(memories);

      document.getElementById("citizen-loading").classList.add("d-none");
      document.getElementById("citizen-content").classList.remove("d-none");
    } catch (err) {
      document.getElementById("citizen-loading").classList.add("d-none");
      const errBox = document.getElementById("citizen-error");
      errBox.textContent = err.message;
      errBox.classList.remove("d-none");
    }
  }

  function showManageFeedback(message, isError) {
    const box = document.getElementById("manage-feedback");
    box.innerHTML = `<div class="${isError ? "alert-asim-error" : "alert alert-light border"}" style="font-size:0.82rem; padding:0.4rem 0.6rem;">${escapeHtml(message)}</div>`;
    setTimeout(() => (box.innerHTML = ""), 4000);
  }

  async function populateJobOptions() {
    const select = document.getElementById("assign-job-select");
    try {
      const options = await CitizensApi.options();
      (options.jobs || []).forEach((job) => {
        if (job === "unemployed") return; // already the default option
        const opt = document.createElement("option");
        opt.value = job;
        opt.textContent = job;
        select.appendChild(opt);
      });
    } catch (_) {
      // non-fatal — "unemployed" remains selectable
    }
  }

  document.getElementById("assign-job-btn").addEventListener("click", async () => {
    const job = document.getElementById("assign-job-select").value;
    try {
      await CitizensApi.update(citizenId, { job });
      showManageFeedback(`Job set to ${job}.`, false);
      load();
    } catch (err) {
      showManageFeedback(err.message, true);
    }
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

  if (!Auth.isLoggedIn()) {
    document.getElementById("manage-login-notice").classList.remove("d-none");
    document.getElementById("manage-controls").classList.add("d-none");
  } else {
    populateJobOptions();
  }

  // Live updates: if this citizen just posted/purchased/etc., refresh.
  document.addEventListener("asim:ws-message", (e) => {
    const d = e.detail;
    if (String(d.citizen_id) === String(citizenId)) {
      load();
    }
  });

  load();
})();

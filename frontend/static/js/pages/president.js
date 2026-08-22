/**
 * The Presidency — the admin's government console.
 */
(function () {
  AsimNav.render("president");
  AsimSocket.init();

  let government = null;
  let candidates = [];
  let adultAge = null;
  let seatTarget = null; // { citizenId, name } while the seat modal is open

  const genderLabels = {};

  function genderLabel(value) {
    return genderLabels[value] || value || "—";
  }

  function esc(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function feedback(message, isError) {
    const box = document.getElementById("gov-feedback");
    box.innerHTML = `<div class="${isError ? "alert-asim-error" : "alert alert-light border"}" style="font-size:0.88rem;">${esc(message)}</div>`;
    if (!isError) setTimeout(() => (box.innerHTML = ""), 5000);
  }

  // ------------------------------------------------------------ office cards

  function officeBody(office, holder) {
    if (!holder) {
      return `
        <div class="flex-grow-1">
          <div class="text-ink-soft mb-2" style="font-size:0.95rem;">Vacant</div>
          <p class="text-ink-faint small mb-0">Pick someone from the candidates below to fill this office.</p>
        </div>`;
    }

    const detail = candidates.find((c) => c.citizen_id === holder.citizen_id);
    const meta = detail
      ? `Age ${detail.age} · ${esc(genderLabel(detail.gender))} · ${esc(detail.job)}`
      : "No longer among the eligible candidates";
    const nationalId = detail && detail.national_id ? esc(detail.national_id) : null;

    return `
      ${AsimAvatar.plainImg(holder.citizen_id, 56)}
      <div class="flex-grow-1 min-width-0">
        <div class="font-display" style="font-size:1.15rem; font-weight:700;">${esc(holder.name)}</div>
        <div class="text-ink-faint small">${meta}</div>
        ${nationalId ? `<div class="text-ink-faint small mono">ID ${nationalId}</div>` : ""}
        <div class="d-flex gap-2 mt-2 flex-wrap">
          <a class="btn btn-sm btn-outline-asim" href="citizen.html?id=${holder.citizen_id}">Profile</a>
          <button class="btn btn-sm btn-outline-asim" data-vacate="${office}">Vacate</button>
        </div>
      </div>`;
  }

  function renderOffices() {
    const president = government ? government.president : null;
    const firstLady = government ? government.first_lady : null;

    document.getElementById("president-body").innerHTML = officeBody("president", president);
    document.getElementById("first-lady-body").innerHTML = officeBody("first_lady", firstLady);

    document.getElementById("office-president").style.borderColor = president
      ? "rgba(91,141,239,0.45)"
      : "";
    document.getElementById("office-first-lady").style.borderColor = firstLady
      ? "rgba(91,141,239,0.45)"
      : "";

    document.querySelectorAll("[data-vacate]").forEach((btn) => {
      btn.addEventListener("click", () => vacate(btn.dataset.vacate));
    });
  }

  function renderSubtitle() {
    const sub = document.getElementById("gov-subtitle");
    if (!government) {
      sub.textContent = "No government has been established yet.";
      return;
    }
    const capital = government.capital_city_name
      ? `Seat of government: ${government.capital_city_name}`
      : "No capital city assigned";
    const term = `in office since tick ${government.term_started_tick}`;
    const who = government.president
      ? `${government.president.name} ${term}`
      : "The presidency is vacant";
    sub.textContent = `${who} · ${capital}`;
  }

  function renderPolicy() {
    if (!government) return;
    document.getElementById("policy-tax").value = (government.tax_rate * 100).toFixed(1);
    document.getElementById("policy-curfew").checked = !!government.curfew_enabled;
  }

  // -------------------------------------------------------------- parliament

  function parliamentRow(m) {
    const party = m.party ? esc(m.party) : "Independent";
    const flag = m.is_alive
      ? ""
      : ` <span class="text-danger-asim small">(deceased — seat should be vacated)</span>`;
    return `
      <div class="product-row align-items-center">
        <div class="d-flex align-items-center gap-2 min-width-0">
          <span class="mono text-ink-faint" style="width:2.5rem;">#${m.seat_number}</span>
          ${AsimAvatar.plainImg(m.citizen_id, 30)}
          <div class="min-width-0">
            <a href="citizen.html?id=${m.citizen_id}" class="text-decoration-none" style="color:inherit; font-weight:600;">${esc(m.name)}</a>${flag}
            <div class="text-ink-faint" style="font-size:0.76rem;">${party} · age ${m.age} · ${esc(m.job)}</div>
          </div>
        </div>
        <div class="d-flex align-items-center gap-2">
          <button class="btn btn-sm btn-outline-asim" data-unseat="${m.id}" data-name="${esc(m.name)}">Remove</button>
        </div>
      </div>`;
  }

  function renderParliament(chamber) {
    document.getElementById("parliament-count").textContent =
      `${chamber.seats_filled} of ${chamber.seats_total} seats filled · ${chamber.seats_available} free`;

    const list = document.getElementById("parliament-list");
    if (!chamber.items.length) {
      list.innerHTML = `<div class="text-ink-faint small">No seats filled yet. Seat someone from the candidates below.</div>`;
      return;
    }
    list.innerHTML = chamber.items.map(parliamentRow).join("");
    list.querySelectorAll("[data-unseat]").forEach((btn) => {
      btn.addEventListener("click", () => unseat(btn.dataset.unseat, btn.dataset.name));
    });
  }

  // -------------------------------------------------------------- candidates

  function roleBadges(c) {
    if (!c.current_roles.length) return "";
    return c.current_roles
      .map(
        (r) =>
          `<span class="badge-category" style="margin-left:0.35rem;">${esc(r)}</span>`
      )
      .join("");
  }

  function candidateRow(c) {
    const presidentDisabled = c.is_president ? " disabled" : "";
    const firstLadyDisabled = c.is_first_lady ? " disabled" : "";
    const mpDisabled = c.is_parliament_member ? " disabled" : "";

    return `
      <div class="product-row align-items-center" data-candidate-row="${c.citizen_id}">
        <div class="d-flex align-items-center gap-2 min-width-0">
          ${AsimAvatar.plainImg(c.citizen_id, 34)}
          <div class="min-width-0">
            <div>
              <a href="citizen.html?id=${c.citizen_id}" class="text-decoration-none" style="color:inherit; font-weight:600;">${esc(c.name)}</a>${roleBadges(c)}
            </div>
            <div class="text-ink-faint" style="font-size:0.76rem;">
              Age ${c.age} · ${esc(genderLabel(c.gender))} · ${esc(c.job)} · ${esc(c.neighborhood || "")}${
                c.national_id ? ` · <span class="mono">${esc(c.national_id)}</span>` : ""
              }
            </div>
          </div>
        </div>
        <div class="d-flex gap-1 flex-wrap justify-content-end">
          <button class="btn btn-sm btn-outline-asim" data-make="president" data-id="${c.citizen_id}" data-name="${esc(c.name)}"${presidentDisabled}>President</button>
          <button class="btn btn-sm btn-outline-asim" data-make="first_lady" data-id="${c.citizen_id}" data-name="${esc(c.name)}"${firstLadyDisabled}>First Lady</button>
          <button class="btn btn-sm btn-outline-asim" data-make="mp" data-id="${c.citizen_id}" data-name="${esc(c.name)}"${mpDisabled}>Parliament</button>
        </div>
      </div>`;
  }

  function visibleCandidates() {
    const search = document.getElementById("candidate-search").value.trim().toLowerCase();
    const gender = document.getElementById("candidate-gender").value;
    return candidates.filter((c) => {
      if (gender && c.gender !== gender) return false;
      if (!search) return true;
      const nid = (c.national_id || "").toLowerCase();
      return c.name.toLowerCase().includes(search) || nid.includes(search);
    });
  }

  function renderCandidates() {
    const list = document.getElementById("candidate-list");
    const shown = visibleCandidates();

    document.getElementById("candidate-note").textContent =
      adultAge == null
        ? `${candidates.length} eligible`
        : `${shown.length} of ${candidates.length} eligible citizens shown — living and at least ${adultAge} years old.`;

    if (!shown.length) {
      list.innerHTML = `<div class="empty-state">${
        candidates.length
          ? "No candidate matches that filter."
          : "No eligible candidates. Add citizens, or wait for the young ones to grow up."
      }</div>`;
      return;
    }

    list.innerHTML = shown.map(candidateRow).join("");
    list.querySelectorAll("[data-make]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = parseInt(btn.dataset.id, 10);
        const name = btn.dataset.name;
        if (btn.dataset.make === "president") appoint("president", id, name);
        else if (btn.dataset.make === "first_lady") appoint("first_lady", id, name);
        else openSeatModal(id, name);
      });
    });
  }

  async function populateGenderFilter() {
    const select = document.getElementById("candidate-gender");
    try {
      const options = await CitizensApi.options();
      (options.genders || []).forEach((g) => {
        genderLabels[g.value] = g.label;
        const opt = document.createElement("option");
        opt.value = g.value;
        opt.textContent = g.label;
        select.appendChild(opt);
      });
    } catch (_) {}
  }

  // ------------------------------------------------------------------ actions

  async function appoint(office, citizenId, name) {
    const label = office === "president" ? "President" : "First Lady";
    try {
      government =
        office === "president"
          ? await GovernmentApi.setPresident(citizenId)
          : await GovernmentApi.setFirstLady(citizenId);
      feedback(`${name} is now ${label}.`, false);
      await refreshCandidates();
      renderAll();
    } catch (err) {
      feedback(`Action failed: ${err.message}`, true);
    }
  }

  async function vacate(office) {
    const label = office === "president" ? "the presidency" : "the office of First Lady";
    if (!window.confirm(`Leave ${label} vacant?`)) return;
    try {
      government =
        office === "president"
          ? await GovernmentApi.setPresident(null)
          : await GovernmentApi.setFirstLady(null);
      feedback(`Vacated ${label}.`, false);
      await refreshCandidates();
      renderAll();
    } catch (err) {
      feedback(`Action failed: ${err.message}`, true);
    }
  }

  function openSeatModal(citizenId, name) {
    seatTarget = { citizenId, name };
    document.getElementById("seat-error").classList.add("d-none");
    document.getElementById("seat-form").reset();
    document.getElementById("seat-who").textContent = `Seating ${name}. Leave the seat number blank to take the lowest free seat.`;
    new bootstrap.Modal(document.getElementById("seat-modal")).show();
  }

  async function unseat(memberId, name) {
    if (!window.confirm(`Remove ${name} from parliament? They keep their life and their history — only the seat is vacated.`)) {
      return;
    }
    try {
      const result = await GovernmentApi.removeMp(memberId);
      feedback(`Removed ${result.name || name} from seat ${result.seat_number}.`, false);
      await loadParliament();
      await refreshCandidates();
      renderCandidates();
    } catch (err) {
      feedback(`Action failed: ${err.message}`, true);
    }
  }

  document.getElementById("seat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!seatTarget) return;
    const errorBox = document.getElementById("seat-error");
    errorBox.classList.add("d-none");

    const party = document.getElementById("seat-party").value.trim();
    const seatNumber = document.getElementById("seat-number").value;

    try {
      const member = await GovernmentApi.appointMp(
        seatTarget.citizenId,
        party || null,
        seatNumber ? parseInt(seatNumber, 10) : null
      );
      bootstrap.Modal.getInstance(document.getElementById("seat-modal")).hide();
      feedback(`${member.name} took seat ${member.seat_number}.`, false);
      seatTarget = null;
      await loadParliament();
      await refreshCandidates();
      renderCandidates();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove("d-none");
    }
  });

  document.getElementById("policy-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const taxPercent = parseFloat(document.getElementById("policy-tax").value);
    if (Number.isNaN(taxPercent)) {
      feedback("Enter a tax rate between 0 and 100.", true);
      return;
    }
    try {
      government = await GovernmentApi.update({
        tax_rate: taxPercent / 100,
        curfew_enabled: document.getElementById("policy-curfew").checked,
      });
      feedback("Policy saved.", false);
      renderPolicy();
    } catch (err) {
      feedback(`Policy save failed: ${err.message}`, true);
    }
  });

  document.getElementById("auto-appoint-btn").addEventListener("click", async () => {
    const btn = document.getElementById("auto-appoint-btn");
    btn.disabled = true;
    try {
      government = await GovernmentApi.autoAppoint();
      feedback("Filled any vacant office.", false);
      await refreshCandidates();
      renderAll();
    } catch (err) {
      feedback(`Auto-appoint failed: ${err.message}`, true);
    } finally {
      btn.disabled = false;
    }
  });

  ["candidate-search", "candidate-gender"].forEach((id) => {
    document.getElementById(id).addEventListener("input", renderCandidates);
  });

  // ------------------------------------------------------------------- load

  function renderAll() {
    renderSubtitle();
    renderOffices();
    renderPolicy();
    renderCandidates();
  }

  async function refreshCandidates() {
    const result = await GovernmentApi.candidates();
    candidates = result.items || [];
    adultAge = result.adult_age;
  }

  async function loadParliament() {
    try {
      renderParliament(await GovernmentApi.parliament());
    } catch (err) {
      document.getElementById("parliament-list").innerHTML =
        `<div class="alert-asim-error">${esc(err.message)}</div>`;
    }
  }

  async function load() {
    try {
      government = await GovernmentApi.get();
    } catch (err) {
      government = null;
    }

    try {
      await refreshCandidates();
    } catch (err) {
      document.getElementById("candidate-list").innerHTML =
        `<div class="alert-asim-error">${esc(err.message)}</div>`;
    }

    renderAll();
    await loadParliament();
  }

  document.addEventListener("asim:ws-message", (event) => {
    if (event.detail && event.detail.type === "citizen_died") load();
  });

  populateGenderFilter().then(load);
})();
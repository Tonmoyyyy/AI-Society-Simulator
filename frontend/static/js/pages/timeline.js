(function () {
  AsimNav.render("timeline");
  AsimSocket.init();

  const PAGE_SIZE = 20;
  let page = 1;
  let category = "";
  let totalLoaded = 0;
  let grandTotal = 0;

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function eventHtml(evt) {
    return `
      <div class="timeline-event category-${escapeHtml(evt.category)}">
        <div class="event-tick">Tick ${evt.tick_number}</div>
        <div class="event-title">${escapeHtml(evt.title)}</div>
        <div class="event-desc">${escapeHtml(evt.description)}</div>
      </div>`;
  }

  async function loadInitial() {
    const list = document.getElementById("timeline-list");
    list.innerHTML = '<div class="text-ink-faint small">Loading…</div>';
    try {
      const result = await DashboardApi.timeline(1, PAGE_SIZE, category || null);
      page = 1;
      grandTotal = result.total;
      totalLoaded = result.items.length;
      if (!result.items.length) {
        list.innerHTML = '<div class="empty-state">No history yet. Run some ticks to see the civilization evolve.</div>';
      } else {
        list.innerHTML = result.items.map(eventHtml).join("");
      }
      updateLoadMoreVisibility();
    } catch (err) {
      list.innerHTML = `<div class="alert-asim-error">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadMore() {
    page += 1;
    const result = await DashboardApi.timeline(page, PAGE_SIZE, category || null);
    document
      .getElementById("timeline-list")
      .insertAdjacentHTML("beforeend", result.items.map(eventHtml).join(""));
    totalLoaded += result.items.length;
    updateLoadMoreVisibility();
  }

  function updateLoadMoreVisibility() {
    document.getElementById("load-more-btn").classList.toggle("d-none", totalLoaded >= grandTotal);
  }

  document.getElementById("load-more-btn").addEventListener("click", loadMore);
  document.getElementById("category-filter").addEventListener("change", (e) => {
    category = e.target.value;
    loadInitial();
  });

  document.addEventListener("asim:ws-message", (e) => {
    const msg = e.detail;
    if (msg.type !== "new_milestone") return;
    if (category && msg.category !== category) return;
    const list = document.getElementById("timeline-list");
    const emptyState = list.querySelector(".empty-state");
    if (emptyState) list.innerHTML = "";
    list.insertAdjacentHTML(
      "afterbegin",
      eventHtml({ category: msg.category, title: msg.title, description: msg.description, tick_number: "…" })
    );
    grandTotal += 1;
    totalLoaded += 1;
  });

  loadInitial();
})();

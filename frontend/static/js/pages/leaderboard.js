(function () {
  AsimNav.render("leaderboard");
  AsimSocket.init();

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function moneyFormat(value) {
    return "$" + Number(value).toFixed(2);
  }

  function medal(rank) {
    if (rank === 1) return "🥇";
    if (rank === 2) return "🥈";
    if (rank === 3) return "🥉";
    return `#${rank}`;
  }

  async function load() {
    const container = document.getElementById("leaderboard-list");
    try {
      const entries = await DashboardLeaderboardApi.get(50);
      if (!entries.length) {
        container.innerHTML = '<div class="empty-state">No citizens with a wallet yet.</div>';
        return;
      }
      container.innerHTML = entries
        .map(
          (e, i) => `
          <div class="d-flex justify-content-between align-items-center py-2${i > 0 ? " border-top" : ""}">
            <div class="d-flex align-items-center gap-3">
              <span class="mono text-ink-faint" style="width:2.2rem; text-align:center;">${medal(i + 1)}</span>
              <div>
                <a href="citizen.html?id=${e.citizen_id}" class="fw-semibold" style="font-family: var(--font-display); color: var(--ink);">${escapeHtml(e.name)}</a>
                <div class="text-ink-faint small">${escapeHtml(e.job)} · ${escapeHtml(e.neighborhood)}</div>
              </div>
            </div>
            <span class="mono fw-semibold">${moneyFormat(e.balance)}</span>
          </div>`
        )
        .join("");
    } catch (err) {
      container.innerHTML = `<div class="alert-asim-error">${escapeHtml(err.message)}</div>`;
    }
  }

  document.addEventListener("asim:ws-message", (e) => {
    if (e.detail.type === "new_purchase" || e.detail.type === "new_milestone") {
      load();
    }
  });

  load();
})();

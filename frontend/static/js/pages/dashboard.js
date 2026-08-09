(function () {
  AsimNav.render("dashboard");
  AsimSocket.init();

  const moneyFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

  let wellbeingChart = null;

  function renderStats(stats) {
    document.getElementById("stat-population").textContent = stats.population;
    document.getElementById("stat-employed").textContent = stats.employed_count;
    document.getElementById("stat-unemployed-sub").textContent =
      `${stats.unemployed_count} unemployed`;
    document.getElementById("stat-money").textContent =
      "$" + moneyFormatter.format(Number(stats.total_money_in_economy));

    const richestEl = document.getElementById("stat-richest");
    const richestSubEl = document.getElementById("stat-richest-sub");
    if (stats.richest_citizen) {
      richestEl.textContent = stats.richest_citizen.name;
      richestSubEl.textContent = "$" + moneyFormatter.format(Number(stats.richest_citizen.balance));
    } else {
      richestEl.textContent = "—";
      richestSubEl.textContent = "No one has earned yet";
    }

    renderWellbeingChart(stats);
  }

  function renderWellbeingChart(stats) {
    const ctx = document.getElementById("wellbeing-chart");
    const data = {
      labels: ["Happiness", "Energy", "Health"],
      datasets: [
        {
          data: [stats.average_happiness, stats.average_energy, stats.average_health],
          backgroundColor: ["#e8a33d", "#2f6f6b", "#c1443c"],
          borderRadius: 6,
          maxBarThickness: 56,
        },
      ],
    };
    const options = {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { min: 0, max: 100, ticks: { stepSize: 20 } } },
    };

    if (wellbeingChart) {
      wellbeingChart.data = data;
      wellbeingChart.update();
    } else {
      wellbeingChart = new Chart(ctx, { type: "bar", data, options });
    }
  }

  function renderTrending(posts) {
    const container = document.getElementById("trending-list");
    if (!posts.length) {
      container.innerHTML = '<div class="text-ink-faint small">No posts yet — run a tick or two.</div>';
      return;
    }
    container.innerHTML = posts
      .map(
        (p) => `
        <div class="mb-3 pb-3 border-bottom">
          <div class="d-flex justify-content-between">
            <span class="fw-semibold" style="font-family: var(--font-display);">${escapeHtml(p.citizen_name)}</span>
            <span class="text-ink-faint small mono">${p.comment_count + p.reaction_count} engaged</span>
          </div>
          <div class="small mt-1">${escapeHtml(p.content)}</div>
        </div>`
      )
      .join("");
  }

  function renderTimeline(events) {
    const container = document.getElementById("recent-timeline");
    if (!events.length) {
      container.innerHTML = '<div class="text-ink-faint small">Nothing recorded yet.</div>';
      return;
    }
    container.innerHTML = events
      .slice(0, 5)
      .map(
        (e) => `
        <div class="timeline-event category-${escapeHtml(e.category)}">
          <div class="event-tick">Tick ${e.tick_number}</div>
          <div class="event-title" style="font-size:0.92rem;">${escapeHtml(e.title)}</div>
        </div>`
      )
      .join("");
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function showTickFeedback(message, isError) {
    const box = document.getElementById("tick-feedback");
    box.innerHTML = `<div class="${isError ? "alert-asim-error" : "alert alert-light border"}" style="font-size:0.88rem;">${escapeHtml(message)}</div>`;
    setTimeout(() => {
      box.innerHTML = "";
    }, 4000);
  }

  async function loadAll() {
    try {
      const stats = await DashboardApi.stats();
      renderStats(stats);
    } catch (err) {
      showTickFeedback(err.message, true);
    }
    try {
      const trending = await DashboardApi.trending(5);
      renderTrending(trending);
    } catch (_) {
      /* non-fatal */
    }
    try {
      const timeline = await DashboardApi.timeline(1, 5);
      renderTimeline(timeline.items);
    } catch (_) {
      /* non-fatal */
    }
  }

  document.getElementById("trigger-tick-btn").addEventListener("click", async () => {
    if (!Auth.isLoggedIn()) {
      window.location.href = "login.html";
      return;
    }
    const btn = document.getElementById("trigger-tick-btn");
    btn.disabled = true;
    btn.textContent = "Running…";
    try {
      const result = await SimulationApi.triggerTick();
      showTickFeedback(
        `Tick ${result.tick_number} completed — ${result.citizens_processed} citizens processed.`,
        false
      );
      await loadAll();
    } catch (err) {
      showTickFeedback(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "Run one tick";
    }
  });

  // Live updates: a new milestone means dashboard state likely changed too.
  document.addEventListener("asim:ws-message", (e) => {
    if (e.detail.type === "new_milestone") {
      loadAll();
    }
  });

  loadAll();
})();

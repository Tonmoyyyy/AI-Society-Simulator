/**
 * Injects the shared nav into <div id="asim-nav"></div>. Call
 * AsimNav.render("dashboard") with the current page's key so the right
 * link gets the active state. Kept as runtime injection (not a template
 * engine) since v0.1 deliberately has no build step.
 */
const AsimNav = (() => {
  const LINKS = [
    { key: "dashboard", href: "dashboard.html", label: "Dashboard" },
    { key: "citizens", href: "citizens.html", label: "Citizens" },
    { key: "feed", href: "feed.html", label: "Feed" },
    { key: "shops", href: "shops.html", label: "Marketplace" },
    { key: "leaderboard", href: "leaderboard.html", label: "Leaderboard" },
    { key: "timeline", href: "timeline.html", label: "Timeline" },
  ];

  function render(activeKey) {
    const mount = document.getElementById("asim-nav");
    if (!mount) return;

    const linksHtml = LINKS.map(
      (l) =>
        `<a class="nav-link${l.key === activeKey ? " active" : ""}" href="${l.href}">${l.label}</a>`
    ).join("");

    const email = typeof Auth !== "undefined" ? Auth.getEmail() : null;

    mount.innerHTML = `
      <nav class="asim-nav">
        <div class="container-fluid px-3 px-md-4">
          <div class="d-flex align-items-center justify-content-between py-2 flex-wrap gap-2">
            <div class="d-flex align-items-center gap-4 flex-wrap">
              <a href="dashboard.html" class="brand">
                <span>AI Society Simulator</span>
              </a>
              <div class="d-none d-md-flex gap-1">${linksHtml}</div>
            </div>
            <div class="d-flex align-items-center gap-3">
              <span class="sim-pulse" title="Live feed connection">
                <span class="dot"></span><span class="pulse-label">Offline</span>
              </span>
              ${
                email
                  ? `<span class="text-ink-faint small d-none d-sm-inline">${email}</span>
                     <button id="asim-logout-btn" class="btn btn-sm btn-outline-asim">Log out</button>`
                  : `<a href="login.html" class="btn btn-sm btn-asim-amber">Log in</a>`
              }
            </div>
          </div>
          <div class="d-flex d-md-none gap-1 pb-2">${linksHtml}</div>
        </div>
      </nav>
    `;

    const logoutBtn = document.getElementById("asim-logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => AuthApi.logout());
    }
  }

  return { render };
})();

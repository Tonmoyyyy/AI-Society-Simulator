(function () {
  AsimNav.render("feed");
  AsimSocket.init();

  const PAGE_SIZE = 15;
  let page = 1;
  let totalLoaded = 0;
  let grandTotal = 0;

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function timeAgo(isoString) {
    const seconds = Math.floor((Date.now() - new Date(isoString + "Z")) / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  }

  function postHtml(post, isNew) {
    return `
      <div class="feed-post${isNew ? " is-new" : ""}" data-post-id="${post.id}">
        <div class="d-flex justify-content-between align-items-baseline">
          <span class="post-author">${escapeHtml(post.citizen_name)}</span>
          <span class="post-time">${timeAgo(post.created_at)}</span>
        </div>
        <div class="post-content">${escapeHtml(post.content)}</div>
        <div class="post-actions">
          <span>💬 ${post.comment_count}</span>
          <span>❤ ${post.reaction_count}</span>
        </div>
      </div>`;
  }

  async function loadInitial() {
    const list = document.getElementById("feed-list");
    try {
      const result = await FeedApi.list(1, PAGE_SIZE);
      grandTotal = result.total;
      totalLoaded = result.items.length;
      if (!result.items.length) {
        list.innerHTML = '<div class="empty-state">No posts yet. Run a tick on the dashboard to bring citizens to life.</div>';
      } else {
        list.innerHTML = result.items.map((p) => postHtml(p, false)).join("");
      }
      updateLoadMoreVisibility();
    } catch (err) {
      list.innerHTML = `<div class="alert-asim-error">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadMore() {
    page += 1;
    const result = await FeedApi.list(page, PAGE_SIZE);
    const list = document.getElementById("feed-list");
    list.insertAdjacentHTML("beforeend", result.items.map((p) => postHtml(p, false)).join(""));
    totalLoaded += result.items.length;
    updateLoadMoreVisibility();
  }

  function updateLoadMoreVisibility() {
    const btn = document.getElementById("load-more-btn");
    btn.classList.toggle("d-none", totalLoaded >= grandTotal);
  }

  document.getElementById("load-more-btn").addEventListener("click", loadMore);

  // Realtime: prepend new posts as they happen (from the tick engine or
  // the manual create-post endpoint), no polling needed.
  document.addEventListener("asim:ws-message", (e) => {
    const msg = e.detail;
    if (msg.type !== "new_post") return;
    const list = document.getElementById("feed-list");
    const emptyState = list.querySelector(".empty-state");
    if (emptyState) list.innerHTML = "";

    const fakePost = {
      id: msg.post_id,
      citizen_name: msg.citizen_name,
      content: msg.content,
      created_at: new Date().toISOString().replace("Z", ""),
      comment_count: 0,
      reaction_count: 0,
    };
    list.insertAdjacentHTML("afterbegin", postHtml(fakePost, true));
    grandTotal += 1;
    totalLoaded += 1;
  });

  loadInitial();
})();

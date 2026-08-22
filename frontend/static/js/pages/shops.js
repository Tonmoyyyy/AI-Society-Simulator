(function () {
  AsimNav.render("shops");
  AsimSocket.init();

  // ATTRIBUTE-SAFE — see the same note in pages/citizens.js. The output goes
  // into `data-shop-name="..."`, and the textContent/innerHTML trick does not
  // escape quotes, so a shop name containing one would break out of it.
  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showFeedback(message, isError) {
    const box = document.getElementById("shops-feedback");
    box.innerHTML = `<div class="${isError ? "alert-asim-error" : "alert alert-light border"}" style="font-size:0.88rem;">${escapeHtml(message)}</div>`;
    setTimeout(() => (box.innerHTML = ""), 4000);
  }

  function shopCard(shop) {
    const productsHtml = shop.products.length
      ? shop.products
          .map(
            (p) => `
        <div class="product-row">
          <span>${escapeHtml(p.name)}</span>
          <span class="product-price">$${Number(p.price).toFixed(2)}</span>
        </div>`
          )
          .join("")
      : '<div class="text-ink-faint small py-2">No products yet.</div>';

    return `
      <div class="col-sm-6 col-lg-4">
        <div class="shop-card">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div class="shop-name">${escapeHtml(shop.name)}</div>
            <span class="badge-category">${escapeHtml(shop.category)}</span>
          </div>
          <div class="mb-2">${productsHtml}</div>
          <button class="btn btn-sm btn-outline-asim add-product-btn" data-shop-id="${shop.id}" data-shop-name="${escapeHtml(shop.name)}">
            + Add product
          </button>
        </div>
      </div>`;
  }

  async function loadShops() {
    const grid = document.getElementById("shops-grid");
    try {
      const shops = await ShopApi.list();
      if (!shops.length) {
        grid.innerHTML = '<div class="col-12"><div class="empty-state">No shops yet. Create the first one.</div></div>';
      } else {
        grid.innerHTML = shops.map(shopCard).join("");
      }
      grid.querySelectorAll(".add-product-btn").forEach((btn) => {
        btn.addEventListener("click", () => openProductModal(btn.dataset.shopId, btn.dataset.shopName));
      });
    } catch (err) {
      grid.innerHTML = `<div class="col-12"><div class="alert-asim-error">${escapeHtml(err.message)}</div></div>`;
    }
  }

  function openProductModal(shopId, shopName) {
    if (!Auth.isLoggedIn()) {
      window.location.href = "login.html";
      return;
    }
    document.getElementById("new-product-shop-id").value = shopId;
    document.getElementById("new-product-shop-name").textContent = shopName;
    document.getElementById("new-product-error").classList.add("d-none");
    document.getElementById("new-product-form").reset();
    new bootstrap.Modal(document.getElementById("new-product-modal")).show();
  }

  document.getElementById("new-shop-btn").addEventListener("click", () => {
    if (!Auth.isLoggedIn()) {
      window.location.href = "login.html";
      return;
    }
    document.getElementById("new-shop-error").classList.add("d-none");
    document.getElementById("new-shop-form").reset();
    new bootstrap.Modal(document.getElementById("new-shop-modal")).show();
  });

  document.getElementById("new-shop-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorBox = document.getElementById("new-shop-error");
    errorBox.classList.add("d-none");
    const name = document.getElementById("new-shop-name").value.trim();
    const category = document.getElementById("new-shop-category").value.trim();
    try {
      await ShopApi.createShop(name, category);
      bootstrap.Modal.getInstance(document.getElementById("new-shop-modal")).hide();
      showFeedback(`"${name}" opened for business.`, false);
      await loadShops();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove("d-none");
    }
  });

  document.getElementById("new-product-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorBox = document.getElementById("new-product-error");
    errorBox.classList.add("d-none");
    const shopId = document.getElementById("new-product-shop-id").value;
    const name = document.getElementById("new-product-name").value.trim();
    const price = parseFloat(document.getElementById("new-product-price").value);
    try {
      await ShopApi.createProduct(shopId, name, price);
      bootstrap.Modal.getInstance(document.getElementById("new-product-modal")).hide();
      showFeedback(`"${name}" added to the shelf.`, false);
      await loadShops();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove("d-none");
    }
  });

  // Realtime: a citizen just bought something — quietly reflected next load,
  // no need to hard-refresh the whole grid on every purchase (prices don't
  // change from purchases, only citizen wallets do).
  document.addEventListener("asim:ws-message", (e) => {
    if (e.detail.type === "new_purchase") {
      showFeedback(`${e.detail.citizen_name} just bought ${e.detail.product_name}.`, false);
    }
  });

  loadShops();
})();

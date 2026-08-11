const ShopApi = {
  async list() {
    return apiFetch("/api/v1/shops");
  },

  async createShop(name, category) {
    return apiFetch("/api/v1/shops", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ name, category }),
    });
  },

  async createProduct(shopId, name, price) {
    return apiFetch(`/api/v1/shops/${shopId}/products`, {
      method: "POST",
      auth: true,
      body: JSON.stringify({ name, price }),
    });
  },
};

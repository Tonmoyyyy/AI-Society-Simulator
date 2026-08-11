const CitizensApi = {
  async list(page = 1, pageSize = 20) {
    return apiFetch(`/api/v1/citizens?page=${page}&page_size=${pageSize}`);
  },

  async get(citizenId) {
    return apiFetch(`/api/v1/citizens/${citizenId}`);
  },

  async create(name) {
    const body = name ? { name } : {};
    return apiFetch("/api/v1/citizens", {
      method: "POST",
      auth: true,
      body: JSON.stringify(body),
    });
  },

  async memories(citizenId, limit = 10) {
    return apiFetch(`/api/v1/citizens/${citizenId}/memories?limit=${limit}`);
  },

  async wallet(citizenId) {
    return apiFetch(`/api/v1/citizens/${citizenId}/wallet`);
  },

  async purchases(citizenId, limit = 10) {
    return apiFetch(`/api/v1/citizens/${citizenId}/purchases?limit=${limit}`);
  },
};

const CitizensApi = {
  async list(page = 1, pageSize = 20) {
    return apiFetch(`/api/v1/citizens?page=${page}&page_size=${pageSize}`);
  },

  async options() {
    return apiFetch("/api/v1/citizens/options");
  },

  async get(citizenId) {
    return apiFetch(`/api/v1/citizens/${citizenId}`);
  },

  async create(fields = {}) {
    // fields can include: name, age, job, neighborhood, personality_json
    // — any omitted field is randomized server-side. Kept backward
    // compatible with the old create(name) call style.
    const body = typeof fields === "string" ? (fields ? { name: fields } : {}) : fields;
    return apiFetch("/api/v1/citizens", {
      method: "POST",
      auth: true,
      body: JSON.stringify(body),
    });
  },

  async update(citizenId, fields) {
    return apiFetch(`/api/v1/citizens/${citizenId}`, {
      method: "PATCH",
      auth: true,
      body: JSON.stringify(fields),
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

  async transfer(citizenId, toCitizenId, amount) {
    return apiFetch(`/api/v1/citizens/${citizenId}/wallet/transfer`, {
      method: "POST",
      auth: true,
      body: JSON.stringify({ to_citizen_id: toCitizenId, amount }),
    });
  },
};

const DashboardLeaderboardApi = {
  async get(limit = 20) {
    return apiFetch(`/api/v1/dashboard/leaderboard?limit=${limit}`);
  },
};

const CitizensApi = {
  /**
   * @param {number} page
   * @param {number} pageSize
   * @param {object} filters - optional { includeDead, gender, search }.
   *   Added as a fourth argument rather than folded into the signature so every
   *   existing `CitizensApi.list(page, size)` call keeps working unchanged —
   *   omitting it means "living citizens only", which is the backend default.
   */
  async list(page = 1, pageSize = 20, filters = {}) {
    const params = new URLSearchParams({ page, page_size: pageSize });
    // Only sent when true: `include_dead=false` and an absent parameter mean the
    // same thing to the backend, and a shorter URL is easier to read in devtools.
    if (filters.includeDead) params.set("include_dead", "true");
    if (filters.gender) params.set("gender", filters.gender);
    if (filters.search) params.set("search", filters.search);
    return apiFetch(`/api/v1/citizens?${params.toString()}`);
  },

  async options() {
    return apiFetch("/api/v1/citizens/options");
  },

  /** Living/deceased split, gender counts and age brackets — all counted server
   * side, so the caller never adds up a page of results and calls it a total. */
  async demographics() {
    return apiFetch("/api/v1/citizens/demographics");
  },

  async get(citizenId) {
    return apiFetch(`/api/v1/citizens/${citizenId}`);
  },

  async create(fields = {}) {
    // fields can include: name, age, gender, job, neighborhood,
    // national_id, personality_json — any omitted field is randomized
    // server-side. Kept backward compatible with the old create(name) call style.
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

  /**
   * Record a death. SOFT — the row, wallet, posts and memories all survive; the
   * citizen simply stops counting as population and loses any office held.
   * Reversible with `revive`. For a row created by mistake use `remove`, which
   * is a real delete.
   *
   * Resolves to { citizen, vacated_offices } — check `vacated_offices` and tell
   * the admin, because killing the President silently empties the presidency.
   */
  async recordDeath(citizenId, cause = null) {
    return apiFetch(`/api/v1/citizens/${citizenId}/death`, {
      method: "POST",
      auth: true,
      body: JSON.stringify(cause ? { cause } : {}),
    });
  },

  /** Undo a death. Does NOT restore any office — someone may already sit there. */
  async revive(citizenId) {
    return apiFetch(`/api/v1/citizens/${citizenId}/revive`, {
      method: "POST",
      auth: true,
    });
  },

  /** Permanent delete, for rows created in error. Not the same as `recordDeath`. */
  async remove(citizenId) {
    return apiFetch(`/api/v1/citizens/${citizenId}`, {
      method: "DELETE",
      auth: true,
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

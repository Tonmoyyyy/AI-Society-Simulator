window.WorldApi = {
  /**
   * The whole world in one request: cities, districts, buildings, roads,
   * citizen markers, government summary, simulation stats.
   */
  async overview({ cityId = null, includeCitizens = true, citizenLimit = null } = {}) {
    const params = new URLSearchParams();
    if (cityId != null) params.set("city_id", cityId);
    if (includeCitizens === false) params.set("include_citizens", "false");
    if (citizenLimit != null) params.set("citizen_limit", citizenLimit);
    const qs = params.toString();
    return apiFetch(`/api/v1/world${qs ? `?${qs}` : ""}`);
  },

  async cities() {
    return apiFetch("/api/v1/world/cities");
  },

  async city(cityId) {
    return apiFetch(`/api/v1/world/cities/${cityId}`);
  },

  async neighborhoods(cityId = null) {
    const qs = cityId != null ? `?city_id=${cityId}` : "";
    return apiFetch(`/api/v1/world/neighborhoods${qs}`);
  },

  async neighborhood(neighborhoodId) {
    return apiFetch(`/api/v1/world/neighborhoods/${neighborhoodId}`);
  },

  async buildings({ cityId = null, neighborhoodId = null, types = null } = {}) {
    const params = new URLSearchParams();
    if (cityId != null) params.set("city_id", cityId);
    if (neighborhoodId != null) params.set("neighborhood_id", neighborhoodId);
    if (Array.isArray(types)) types.forEach((t) => params.append("type", t));
    const qs = params.toString();
    return apiFetch(`/api/v1/world/buildings${qs ? `?${qs}` : ""}`);
  },

  async building(buildingId) {
    return apiFetch(`/api/v1/world/buildings/${buildingId}`);
  },

  async roads(cityId = null) {
    const qs = cityId != null ? `?city_id=${cityId}` : "";
    return apiFetch(`/api/v1/world/roads${qs}`);
  },

  /**
   * Citizen markers for the current tick.
   */
  async citizens({ cityId = null, limit = null } = {}) {
    const params = new URLSearchParams();
    if (cityId != null) params.set("city_id", cityId);
    if (limit != null) params.set("limit", limit);
    const qs = params.toString();
    return apiFetch(`/api/v1/world/citizens${qs ? `?${qs}` : ""}`);
  },

  /** Districts + building types + road kinds, with labels/icons/colours. */
  async legend() {
    return apiFetch("/api/v1/world/legend");
  },

  /**
   * Header stats only (day, tick, population, happiness, latest event).
   */
  async simulation() {
    return apiFetch("/api/v1/world/simulation");
  },

  async government() {
    return apiFetch("/api/v1/world/government");
  },

  // ---- admin ----

  async generate(force = false) {
    return apiFetch(`/api/v1/world/generate${force ? "?force=true" : ""}`, {
      method: "POST",
      auth: true,
    });
  },

  async seed() {
    return apiFetch("/api/v1/world/seed", { method: "POST", auth: true });
  },

  async renameCity(cityId, fields) {
    return apiFetch(`/api/v1/world/cities/${cityId}`, {
      method: "PATCH",
      auth: true,
      body: JSON.stringify(fields),
    });
  },

  async renameNeighborhood(neighborhoodId, fields) {
    return apiFetch(`/api/v1/world/neighborhoods/${neighborhoodId}`, {
      method: "PATCH",
      auth: true,
      body: JSON.stringify(fields),
    });
  },
};

// Global lexical binding support
var WorldApi = window.WorldApi;
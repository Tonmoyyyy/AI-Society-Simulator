/**
 * World / 3D map API client (World Phase 3).
 *
 * A classic <script> like every other api/*.js file — no build step, no import
 * statements — so it keeps working exactly like CitizensApi and DashboardApi.
 *
 * HOW THE ES MODULE REACHES THIS: `const WorldApi` is a global *lexical*
 * binding, so it is visible to later scripts but is NOT a property of `window`
 * (`window.WorldApi` is undefined). The world modules therefore just reference
 * `WorldApi` bare, which works because classic scripts run before deferred
 * modules — see the load-order comment in pages/world.html.
 *
 * Everything here is a thin wrapper over apiFetch. No shaping, no defaults, no
 * palette: the backend owns labels, icons and colours (GET /world/legend), so
 * adding a building type never requires touching the frontend.
 */
const WorldApi = {
  /**
   * The whole world in one request: cities, districts, buildings, roads,
   * citizen markers, government summary, simulation stats.
   *
   * @param {object} opts
   * @param {number|null} opts.cityId        restrict to one city
   * @param {boolean} opts.includeCitizens   false = terrain-only (fast) load
   * @param {number|null} opts.citizenLimit  cap on returned markers
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
    // `type` is a repeatable query param on the backend, hence append() in a
    // loop rather than a comma-joined string.
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
   * Citizen markers for the current tick. This is the endpoint the map
   * re-polls to move citizens between home and work, so it's deliberately
   * separate from the full overview.
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
   * Cheap enough to poll every tick, unlike overview().
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

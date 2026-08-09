const DashboardApi = {
  async stats() {
    return apiFetch("/api/v1/dashboard/stats");
  },

  async trending(limit = 5) {
    return apiFetch(`/api/v1/dashboard/trending?limit=${limit}`);
  },

  async timeline(page = 1, pageSize = 20, category = null) {
    const params = new URLSearchParams({ page, page_size: pageSize });
    if (category) params.set("category", category);
    return apiFetch(`/api/v1/timeline?${params.toString()}`);
  },
};

const SimulationApi = {
  async triggerTick() {
    return apiFetch("/api/v1/simulation/tick", { method: "POST", auth: true });
  },

  async recentTicks(limit = 5) {
    return apiFetch(`/api/v1/simulation/ticks?limit=${limit}`);
  },

  async schedulerStatus() {
    return apiFetch("/api/v1/simulation/scheduler/status");
  },

  async startScheduler() {
    return apiFetch("/api/v1/simulation/scheduler/start", { method: "POST", auth: true });
  },

  async stopScheduler() {
    return apiFetch("/api/v1/simulation/scheduler/stop", { method: "POST", auth: true });
  },
};

const FeedApi = {
  async list(page = 1, pageSize = 20) {
    return apiFetch(`/api/v1/feed?page=${page}&page_size=${pageSize}`);
  },
};

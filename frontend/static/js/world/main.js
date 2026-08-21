/**
 * World map orchestration (World Phases 6, 7 and 8).
 *
 * Owns: data loading, the render loop, the live refresh, the city selector, the
 * header stats and the Phase 8 performance guards. Everything visual lives in
 * scene.js / builders.js; everything DOM lives in panels.js.
 *
 * -------------------------------------------------------------------------
 * HOW "LIVE" WORKS (Phase 7)
 * -------------------------------------------------------------------------
 * The simulation advances on APScheduler ticks in the backend. This page does
 * NOT try to animate between ticks with its own physics — it re-reads
 * GET /api/v1/world/citizens and moves the markers to wherever the backend says
 * they now are. That is what §16 asks for: citizen movement is a consequence of
 * `citizens.current_activity`, not a separate client-side simulation.
 *
 * Two triggers, deliberately:
 *   * a slow poll (every REFRESH_MS) — the reliable baseline
 *   * the existing /ws/feed WebSocket — nudges an immediate refresh when the
 *     backend broadcasts activity, so the map reacts within a second of a tick
 *     without polling aggressively
 *
 * Both are suspended while the tab is hidden (see PAUSE below), because a
 * background tab that keeps a WebGL loop and a poll running is the classic way
 * a "nice visualization" ends up draining a laptop battery.
 */

import { createStage, resizeStage, flyTo, THREE } from "./scene.js";
import { createWorldLayer } from "./builders.js";
import { createPicker } from "./picking.js";
import { createPanel, renderLegend } from "./panels.js";

const REFRESH_MS = 6000;

// Labels and citizen markers are hidden past these camera distances. This is the
// cheapest possible LOD: no geometry swap, just visibility, and it keeps the
// zoomed-out "whole society" view readable as well as fast (§19).
const CITIZEN_VISIBLE_DISTANCE = 1500;

const dom = {};
let stage = null;
let layer = null;
let picker = null;
let panel = null;
let legend = null;
let government = null;
let cities = [];
let selected = null;
let cityFilter = null;
let refreshTimer = null;
let paused = false;
let pendingRefresh = false;

// Monotonic token that identifies the most recent loadWorld() call. Two rapid
// city switches issue two overlapping fetches, and there is no guarantee the
// first one resolves first — if the older response landed last it would rebuild
// the previous city's geometry while the dropdown and `cityFilter` said
// otherwise. Any response whose token is no longer current is discarded.
let loadToken = 0;

// ------------------------------------------------------------------- boot

document.addEventListener("DOMContentLoaded", async () => {
  AsimNav.render("world");
  cacheDom();

  stage = createStage(dom.canvas, dom.labels);
  layer = createWorldLayer(stage);
  panel = createPanel(dom.panel);
  picker = createPicker(stage, layer, { onHover: handleHover, onSelect: handleSelect });

  wireControls();
  startRenderLoop();
  observeResize();
  watchVisibility();

  await loadWorld();
  connectFeed();
  startPolling();
});

function cacheDom() {
  dom.canvas = document.getElementById("world-canvas");
  dom.labels = document.getElementById("world-label-host");
  dom.panel = document.getElementById("world-panel");
  dom.legend = document.getElementById("world-legend-host");
  dom.citySelect = document.getElementById("world-city-select");
  dom.resetBtn = document.getElementById("world-reset-btn");
  dom.refreshBtn = document.getElementById("world-refresh-btn");
  dom.generateBtn = document.getElementById("world-generate-btn");
  dom.status = document.getElementById("world-status");
  dom.stats = document.getElementById("world-stats");
  dom.event = document.getElementById("world-event");
  dom.hover = document.getElementById("world-hover");
  dom.notice = document.getElementById("world-notice");

  // Every id above is dereferenced without a guard from here on, so fail loudly
  // and immediately if the page and this module ever drift apart, rather than
  // dying halfway through boot with a confusing "of null" further down.
  const missing = Object.entries(dom)
    .filter(([, el]) => !el)
    .map(([key]) => key);
  if (missing.length) {
    throw new Error(`world.html is missing element(s) for: ${missing.join(", ")}`);
  }
}

// ------------------------------------------------------------- data loading

async function loadWorld() {
  const token = ++loadToken;
  setStatus("Loading the world…");
  try {
    // Legend first and only once — it never changes between loads, so
    // re-fetching it on every refresh would be wasted bandwidth.
    if (!legend) {
      legend = await WorldApi.legend();
      renderLegend(dom.legend, legend);
    }

    // The overview and the city list are fetched together, but they are NOT
    // interchangeable.
    //
    // WHY TWO CALLS: when cityFilter is set, `data.cities` contains only the
    // selected city. Driving the dropdown off it would shrink the dropdown to
    // that single option, so the user could not switch to another city without
    // first going back to "Entire society" — and the panel's "Fly to this city"
    // button would stop resolving for every other city. /world/cities is always
    // unfiltered and is a small, cheap list, so it owns the selector while the
    // overview owns the geometry.
    const [data, allCities] = await Promise.all([
      WorldApi.overview({ cityId: cityFilter }),
      WorldApi.cities(),
    ]);

    // A newer load started while these two requests were in flight; that one
    // owns the scene now, so drop this result instead of rebuilding over it.
    if (token !== loadToken) return;

    government = data.government;
    cities = allCities || [];

    layer.build(data, legend);
    picker.clear();
    selected = null;
    panel.renderEmpty();

    fillCitySelect(cities);
    renderStats(data.simulation);
    renderNotices(data);

    setStatus(
      data.world_generated
        ? `${data.buildings.length} buildings · ${data.citizens.length} citizens`
        : "World not generated yet"
    );
  } catch (err) {
    if (token !== loadToken) return;
    setStatus(err.message, true);
  }
}

/**
 * Phase 7 refresh: markers and header only.
 *
 * Buildings and roads don't change between ticks, so re-fetching the overview
 * here would re-download the whole world every few seconds. This hits the two
 * cheap endpoints instead — /world/citizens and /world/simulation — in parallel,
 * and writes the positions straight into the existing InstancedMesh.
 */
async function refreshCitizens() {
  if (paused) {
    pendingRefresh = true;
    return;
  }
  const token = loadToken;
  try {
    const [citizens, summary] = await Promise.all([
      WorldApi.citizens({ cityId: cityFilter }),
      WorldApi.simulation(),
    ]);

    // A city switch happened mid-flight, so these markers belong to the
    // previous filter and the mesh they were meant for has been rebuilt.
    // Writing them now would show the wrong city's citizens until the next poll.
    if (token !== loadToken) return;

    layer.updateCitizens(citizens);
    renderStats(summary);

    // Keep the open panel and the selection outline attached to the citizen as
    // they move, rather than leaving a stale card behind.
    if (selected?.kind === "citizen") {
      const fresh = citizens.find((c) => c.id === selected.record.id);
      if (fresh) {
        selected = { kind: "citizen", record: fresh };
        panel.render(selected, { legend, government });
        picker.reanchor(selected);
      }
    }
  } catch (err) {
    // A failed refresh must not blank the map — the last good state stays on
    // screen and we just note it in the status line.
    setStatus(err.message, true);
  }
}

// ------------------------------------------------------------------ header

/**
 * @param {object} summary a WorldSimulationOut payload (from either
 *   `overview().simulation` or the standalone /world/simulation route).
 */
function renderStats(summary) {
  const s = summary || {};
  const items = [
    ["Day", s.day ?? "—"],
    ["Tick", s.tick_number ?? "—"],
    ["Population", s.population ?? "—"],
    ["Cities", s.city_count ?? "—"],
    ["Districts", s.neighborhood_count ?? "—"],
    ["Avg happiness", s.average_happiness != null ? Number(s.average_happiness).toFixed(1) : "—"],
  ];
  // Only shown once the Government system exists — never a hardcoded name.
  if (government?.system_available && government.president_name) {
    items.push(["President", government.president_name]);
  }

  dom.stats.innerHTML = items
    .map(
      ([label, value]) =>
        `<div class="world-stat"><span class="world-stat-label">${label}</span>
         <span class="world-stat-value">${value}</span></div>`
    )
    .join("");

  dom.event.textContent = s.current_event ? `Latest: ${s.current_event}` : "";
}

function renderNotices(data) {
  const notices = [];

  if (!data.world_generated) {
    notices.push(
      `The world has no buildings yet. An admin can lay it out with <strong>Generate world</strong> — it's deterministic, so nothing moves on later runs.`
    );
  }
  if (data.unassigned_citizens > 0) {
    notices.push(
      `${data.unassigned_citizens} citizen(s) have no home yet. Run <strong>Generate world</strong> (force) to place them.`
    );
  }
  if (data.citizens_truncated) {
    notices.push(
      `Only the first ${data.citizens.length} citizens are shown. Pick a single city to see the rest.`
    );
  }
  if (data.government && !data.government.system_available) {
    notices.push(
      `The Government / President / First Lady system isn't installed in this backend yet, so the palace has no name on it. The map fills that in automatically once it exists.`
    );
  }

  dom.notice.innerHTML = notices.length
    ? notices.map((n) => `<div class="world-alert">${n}</div>`).join("")
    : "";
}

function setStatus(text, isError = false) {
  dom.status.textContent = text;
  dom.status.classList.toggle("is-error", !!isError);
}

// ------------------------------------------------------------------ controls

function fillCitySelect(list) {
  const current = dom.citySelect.value;
  dom.citySelect.innerHTML =
    `<option value="">Entire society</option>` +
    list
      .map(
        (c) =>
          `<option value="${c.id}">${c.is_capital ? "\u{1F451} " : ""}${c.name} (${c.population})</option>`
      )
      .join("");
  if (current) dom.citySelect.value = current;
}

function wireControls() {
  dom.citySelect.addEventListener("change", async () => {
    const value = dom.citySelect.value;
    cityFilter = value ? Number(value) : null;
    await loadWorld();
    if (cityFilter) {
      const city = cities.find((c) => c.id === cityFilter);
      if (city) flyTo(stage, { x: city.world_x, z: city.world_z }, city.radius * 2.6);
    } else {
      frameWholeWorld();
    }
  });

  // "Whole society" clears the FILTER as well as moving the camera, and it does
  // so by going through the select's own change handler.
  //
  // WHY DISPATCH AN EVENT: assigning `select.value` does not fire `change`, so
  // an earlier version that set the value here left `cityFilter` pointing at the
  // old city — the dropdown read "Entire society" while the map, and every
  // subsequent poll, stayed filtered to one city. Dispatching keeps a single
  // code path for "the filter changed" instead of two that can disagree.
  dom.resetBtn.addEventListener("click", () => {
    if (cityFilter !== null) {
      dom.citySelect.value = "";
      dom.citySelect.dispatchEvent(new Event("change"));
    } else {
      frameWholeWorld();
    }
  });

  dom.refreshBtn.addEventListener("click", () => loadWorld());

  dom.generateBtn.addEventListener("click", async () => {
    // force=true is the only useful mode from the UI: a non-forced call is a
    // no-op the moment any building exists, and the backend already refuses to
    // touch cities, districts, citizens, shops or wallets.
    if (!window.confirm("Rebuild every building and road? Cities, districts and citizens are never deleted.")) {
      return;
    }
    dom.generateBtn.disabled = true;
    setStatus("Generating the world…");
    try {
      const result = await WorldApi.generate(true);
      setStatus(result.detail);
      await loadWorld();
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      dom.generateBtn.disabled = false;
    }
  });

  // "Fly to this city" inside a rendered panel card. Delegated, because the
  // panel's innerHTML is replaced on every selection.
  dom.panel.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-world-focus-city]");
    if (!btn) return;
    const city = cities.find((c) => c.id === Number(btn.dataset.worldFocusCity));
    if (city) flyTo(stage, { x: city.world_x, z: city.world_z }, city.radius * 2.6);
  });

  // Only show the admin action to someone who is actually logged in — the
  // endpoint is require_admin, so showing it to a spectator would just produce
  // a 403.
  if (typeof Auth !== "undefined" && !Auth.isLoggedIn()) {
    dom.generateBtn.classList.add("d-none");
  }
}

/**
 * Pull the camera back to the default overhead view of the whole civilization.
 * Camera only — it deliberately does not touch `cityFilter` or the select, so
 * it is safe to call from inside the change handler without recursing.
 */
function frameWholeWorld() {
  flyTo(stage, { x: 0, z: 0 }, 900);
}

// ------------------------------------------------------------------ picking

function handleHover(found) {
  if (!found) {
    dom.hover.textContent = "";
    dom.hover.classList.remove("is-visible");
    return;
  }

  const r = found.record;
  let text;
  if (found.kind === "citizen") {
    text = `${r.name} — ${r.current_activity}`;
  } else if (found.kind === "building") {
    // Houses store name = NULL, so they're labelled by their owner's live name.
    const title = r.name || (r.owner_name ? `${r.owner_name}'s house` : r.label);
    text = `${r.icon} ${title}`;
  } else if (found.kind === "district") {
    text = `${r.name} — ${r.population} residents`;
  } else {
    text = `${r.name} — ${r.population} citizens`;
  }

  dom.hover.textContent = text;
  dom.hover.classList.add("is-visible");
}

function handleSelect(found) {
  selected = found;
  panel.render(found, { legend, government });
}

// -------------------------------------------------------------- render loop

/**
 * One requestAnimationFrame loop for the whole page.
 *
 * Phase 8 measures live here:
 *   * the loop returns immediately while the tab is hidden
 *   * labels past their maxDistance are hidden (CSS2D labels are real DOM, so
 *     off-screen ones still cost layout)
 *   * the citizen mesh is hidden entirely when zoomed far out, where markers
 *     are sub-pixel anyway
 */
function startRenderLoop() {
  const camPos = new THREE.Vector3();

  function frame() {
    requestAnimationFrame(frame);
    if (paused) return;

    if (stage.flight) stage.flight();
    stage.controls.update();

    camPos.copy(stage.camera.position);
    const targetDistance = camPos.distanceTo(stage.controls.target);

    if (layer.citizenMesh) {
      layer.citizenMesh.visible = targetDistance < CITIZEN_VISIBLE_DISTANCE;
    }

    layer.groups.labels.children.forEach((label) => {
      const max = label.userData.maxDistance ?? Infinity;
      label.visible = camPos.distanceTo(label.position) < max;
    });

    // Landmark flourishes: a slow flag wave and a breathing glow ring around
    // the palace. Cheap (a handful of objects) and it's what makes the capital
    // feel inhabited rather than static.
    const t = performance.now() * 0.001;
    layer.animated.forEach((group) => {
      if (group.userData.flag) {
        group.userData.flag.rotation.y = Math.sin(t * 1.6) * 0.5;
      }
      if (group.userData.glowRing) {
        group.userData.glowRing.material.opacity = 0.32 + Math.sin(t * 1.1) * 0.16;
      }
    });

    stage.renderer.render(stage.scene, stage.camera);
    stage.labelRenderer.render(stage.scene, stage.camera);
  }

  frame();
}

function observeResize() {
  const apply = () =>
    resizeStage(stage, dom.canvas.clientWidth, dom.canvas.clientHeight);
  // ResizeObserver rather than window.onresize: the canvas also changes width
  // when the side panel collapses on a narrow viewport, which no window resize
  // event would report.
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(apply).observe(dom.canvas);
  } else {
    window.addEventListener("resize", apply);
  }
  apply();
}

function watchVisibility() {
  document.addEventListener("visibilitychange", () => {
    paused = document.hidden;
    if (!paused && pendingRefresh) {
      pendingRefresh = false;
      refreshCitizens();
    }
  });
}

// ------------------------------------------------------------ live refresh

function startPolling() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshCitizens, REFRESH_MS);
}

/**
 * Reuse the app's existing /ws/feed socket rather than opening a second one.
 *
 * AsimSocket doesn't take a callback — it re-broadcasts every frame as a DOM
 * event on `document` and drives the nav's live/offline pulse. So this page
 * calls init() (same as every other page) and then listens, exactly like
 * pages/dashboard.js does.
 *
 * Any message means the simulation just did something, which is a reliable
 * "a tick probably landed" signal. Debounced, because one tick can broadcast
 * several events and each must not fire its own HTTP request.
 */
function connectFeed() {
  if (typeof AsimSocket === "undefined") return;

  let debounce = null;
  document.addEventListener("asim:ws-message", () => {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(refreshCitizens, 900);
  });

  AsimSocket.init();
}

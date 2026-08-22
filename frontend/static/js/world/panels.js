/**
 * The information panel and the legend (World Phases 6 and 11).
 *
 * Pure DOM — no Three.js. Given a picked `{ kind, record }` it renders the right
 * card. Kept apart from the renderer so panel copy can change without touching
 * anything that runs per frame.
 *
 * Every label, icon and colour in the legend comes from GET /api/v1/world/legend.
 * Nothing here hardcodes a city name, a district name or a president's name.
 */

const ACTIVITY_ICONS = {
  working: "\u{1F6E0}",
  sleeping: "\u{1F634}",
  eating: "\u{1F37D}",
  socializing: "\u{1F5E3}",
  posting: "\u{1F4F1}",
  idle: "\u{1F4AD}",
};

/**
 * Escape a string for safe interpolation into innerHTML.
 *
 * EXPORTED ON PURPOSE. Every string that reaches this file from the database —
 * citizen names, city names, district names, shop names, the President's name —
 * is ultimately user-supplied: `POST /api/v1/citizens` accepts any name up to
 * 100 characters with no character filtering. So an unescaped interpolation is a
 * stored-XSS hole on a page that is public and unauthenticated. main.js builds
 * innerHTML too and imports this rather than keeping a second copy that could
 * drift.
 *
 * Backend *constants* (icons, colours, legend labels from building_types.py and
 * world_layout.py) are not user input and are interpolated directly.
 */
export function esc(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function num(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

function row(label, value) {
  return `
    <div class="world-row">
      <span class="world-row-label">${esc(label)}</span>
      <span class="world-row-value">${value}</span>
    </div>`;
}

function meter(label, value) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  return `
    <div class="world-meter">
      <div class="world-meter-head">
        <span>${esc(label)}</span><span>${num(pct)}</span>
      </div>
      <div class="world-meter-track"><div class="world-meter-fill" style="width:${pct}%"></div></div>
    </div>`;
}

export function createPanel(mount) {
  function renderEmpty() {
    mount.innerHTML = `
      <div class="world-panel-empty">
        <div class="world-panel-empty-icon">\u{1F5FA}</div>
        <p class="mb-1"><strong>Nothing selected</strong></p>
        <p class="text-ink-faint small mb-0">
          Click a city, a district, a building or a citizen to inspect it.
          Drag to orbit, scroll to zoom.
        </p>
      </div>`;
  }

  function render(found, context = {}) {
    if (!found) return renderEmpty();
    const { kind, record } = found;
    if (kind === "city") mount.innerHTML = cityCard(record, context);
    else if (kind === "district") mount.innerHTML = districtCard(record, context);
    else if (kind === "building") mount.innerHTML = buildingCard(record, context);
    else if (kind === "citizen") mount.innerHTML = citizenCard(record, context);
    else renderEmpty();
  }

  renderEmpty();
  return { render, renderEmpty };
}

// ------------------------------------------------------------------- cards

function cityCard(city, { government }) {
  const isSeat = government?.capital_city_id === city.id;
  return `
    <div class="world-card">
      <div class="world-card-kind">${city.is_capital ? "\u{1F451} Capital city" : "\u{1F3D9} City"}</div>
      <h2 class="world-card-title">${esc(city.name)}</h2>
      <p class="world-card-sub">${esc(city.region)}</p>
      ${city.description ? `<p class="world-card-desc">${esc(city.description)}</p>` : ""}
      ${row("Population", `<strong>${esc(city.population)}</strong>`)}
      ${row("Districts", esc(city.neighborhood_count))}
      ${row("Radius", `${num(city.radius)} units`)}
      ${row("Position", `x ${num(city.world_x)} · z ${num(city.world_z)}`)}
      ${
        isSeat && government?.system_available && government?.president_name
          ? row("President", esc(government.president_name))
          : ""
      }
      <button class="btn btn-sm btn-outline-asim w-100 mt-3" data-world-focus-city="${city.id}">
        Fly to this city
      </button>
    </div>`;
}

function districtCard(district, { legend }) {
  const spec = (legend?.districts || []).find((d) => d.type === district.type);
  return `
    <div class="world-card">
      <div class="world-card-kind">${spec ? `${spec.icon} ${esc(spec.label)} district` : "District"}</div>
      <h2 class="world-card-title">${esc(district.name)}</h2>
      ${district.description ? `<p class="world-card-desc">${esc(district.description)}</p>` : ""}
      ${row("Residents", `<strong>${esc(district.population)}</strong>`)}
      ${row("Size", `${num(district.width)} × ${num(district.depth)}`)}
      ${row("Offset from centre", `x ${num(district.offset_x)} · z ${num(district.offset_z)}`)}
    </div>`;
}

function buildingCard(building, { government }) {
  // A house has name = NULL in the database on purpose; its label is its
  // owner's CURRENT name, resolved by the backend on every request. So a
  // citizen rename shows up here with no regeneration and no code change.
  const title = building.name || (building.owner_name ? `${building.owner_name}'s house` : building.label);

  let extra = "";
  if (building.type === "presidential_palace" && government?.system_available) {
    extra =
      row("President", esc(government.president_name || "Vacant")) +
      row("First Lady", esc(government.first_lady_name || "Vacant")) +
      (government.tax_rate != null ? row("Tax rate", `${num(government.tax_rate * 100, 1)}%`) : "") +
      (government.curfew_enabled != null
        ? row("Curfew", government.curfew_enabled ? "In effect" : "None")
        : "");
  } else if (building.type === "presidential_palace") {
    // system_available is false only when no government row exists at all —
    // i.e. startup seeding never ran. An admin can create one with
    // PATCH /api/v1/government and this panel fills in on the next poll.
    extra = `<p class="world-note">No government has been established yet, so there is no sitting President to show. This panel fills in automatically once one exists.</p>`;
  }

  return `
    <div class="world-card">
      <div class="world-card-kind">${building.icon} ${esc(building.label)}</div>
      <h2 class="world-card-title">${esc(title)}</h2>
      ${building.owner_name ? row("Resident", esc(building.owner_name)) : ""}
      ${building.shop_name ? row("Business", esc(building.shop_name)) : ""}
      ${row("Footprint", `${num(building.width)} × ${num(building.depth)}`)}
      ${row("Height", num(building.height))}
      ${row("Position", `x ${num(building.world_x)} · z ${num(building.world_z)}`)}
      ${extra}
      ${
        building.owner_citizen_id
          ? `<a class="btn btn-sm btn-outline-asim w-100 mt-3" href="citizens.html">Open citizen list</a>`
          : ""
      }
    </div>`;
}

function citizenCard(citizen) {
  const icon = ACTIVITY_ICONS[citizen.current_activity] || "\u{1F464}";
  return `
    <div class="world-card">
      <div class="world-card-kind">\u{1F464} Citizen</div>
      <h2 class="world-card-title world-card-title-serif">${esc(citizen.name)}</h2>
      <p class="world-card-sub">
        ${esc(citizen.job)} · ${esc(citizen.age)} years old
      </p>
      <div class="world-activity ${citizen.at_work ? "is-working" : ""}">
        ${icon} ${esc(citizen.current_activity)}${citizen.at_work ? " · at work" : " · at home"}
      </div>
      ${meter("Mood", citizen.mood)}
      ${meter("Happiness", citizen.happiness)}
      ${row("City", esc(citizen.city_name || "—"))}
      ${row("District", esc(citizen.neighborhood_name || "—"))}
      ${row("Home", citizen.home_building_id ? `#${esc(citizen.home_building_id)}` : "no house yet")}
      ${
        citizen.is_president
          ? `<div class="world-badge">\u{1F451} President</div>`
          : citizen.is_first_lady
          ? `<div class="world-badge">\u{1F338} First Lady</div>`
          : ""
      }
    </div>`;
}

// ------------------------------------------------------------------ legend

/**
 * The legend, built entirely from the backend's payload. Adding a district type
 * or a building type on the server makes it appear here with no frontend edit,
 * which is the whole reason colours and icons live in the API response.
 */
export function renderLegend(mount, legend) {
  if (!legend) return;

  const swatches = (items) =>
    (items || [])
      .map(
        (item) => `
        <li class="world-legend-item">
          <span class="world-swatch" style="background:${esc(item.color)}"></span>
          <span class="world-legend-icon">${item.icon || ""}</span>
          <span>${esc(item.label)}</span>
        </li>`
      )
      .join("");

  mount.innerHTML = `
    <details class="world-legend" open>
      <summary>Legend</summary>
      <div class="world-legend-body">
        <p class="world-legend-head">Districts</p>
        <ul class="world-legend-list">${swatches(legend.districts || [])}</ul>
        <p class="world-legend-head">Buildings</p>
        <ul class="world-legend-list">${swatches(legend.buildings || [])}</ul>
        <p class="world-legend-head">Roads</p>
        <ul class="world-legend-list">${swatches(legend.roads || [])}</ul>
        <p class="world-legend-head">Citizens</p>
        <ul class="world-legend-list">
          <li class="world-legend-item">
            <span class="world-swatch" style="background:#3fbf88"></span>
            <span class="world-legend-icon">\u{1F642}</span><span>Content</span>
          </li>
          <li class="world-legend-item">
            <span class="world-swatch" style="background:#e2685f"></span>
            <span class="world-legend-icon">\u{1F641}</span><span>Unhappy</span>
          </li>
          <li class="world-legend-item">
            <span class="world-swatch" style="background:#f5a623"></span>
            <span class="world-legend-icon">\u{1F6E0}</span><span>At work</span>
          </li>
        </ul>
      </div>
    </details>`;
}

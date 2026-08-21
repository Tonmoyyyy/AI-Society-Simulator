/**
 * Click + hover picking (World Phase 6).
 *
 * Turns a mouse position into a domain object: a city, a district, a building
 * or a citizen. The hard part is InstancedMesh — a thousand houses are ONE
 * object, so the hit has to be resolved through `intersection.instanceId` back
 * into the record array that produced it. That is why builders.js keeps
 * `records` alongside every InstancedMesh it creates.
 */

import { THREE } from "./scene.js";

// Hover raycasts are throttled to ~30/s. Raycasting on every pointermove event
// (which can fire 100+/s) competes with the render loop for the main thread and
// makes the camera feel sticky.
const HOVER_INTERVAL_MS = 33;

// A drag that moves further than this is a camera orbit, not a click. Without
// this, every orbit ends by selecting whatever is under the cursor.
const CLICK_SLOP_PX = 5;

export function createPicker(stage, layer, { onHover, onSelect }) {
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const dom = stage.renderer.domElement;

  let lastHoverAt = 0;
  let downAt = null;
  let hovered = null;

  const highlight = createHighlight(stage);
  const selection = createSelection(stage);

  function toNdc(event) {
    const rect = dom.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }

  /**
   * Raycast targets, in the order builders.js grouped them. Intersections come
   * back sorted by distance, so a citizen standing on a district plate wins
   * naturally — no manual priority list needed.
   */
  function targets() {
    return [
      layer.groups.citizens,
      layer.groups.landmarks,
      layer.groups.buildings,
      layer.groups.districts,
      layer.groups.cities,
    ];
  }

  function pick(event) {
    toNdc(event);
    raycaster.setFromCamera(pointer, stage.camera);
    const hits = raycaster.intersectObjects(targets(), true);
    // Walk the sorted hits until one resolves. Decorative meshes (roof
    // instances, city border rings, landmark columns) resolve to null or to
    // their parent, so this skips them instead of swallowing the click.
    for (const hit of hits) {
      const resolved = resolveHit(hit, layer);
      if (resolved) return resolved;
    }
    return null;
  }

  dom.addEventListener("pointermove", (event) => {
    const now = performance.now();
    if (now - lastHoverAt < HOVER_INTERVAL_MS) return;
    lastHoverAt = now;

    const found = pick(event);
    const sameAsBefore =
      found && hovered && found.kind === hovered.kind && found.record.id === hovered.record.id;
    if (sameAsBefore) return;

    hovered = found;
    dom.style.cursor = found ? "pointer" : "grab";
    placeMarker(highlight, found);
    onHover?.(found);
  });

  dom.addEventListener("pointerleave", () => {
    hovered = null;
    highlight.visible = false;
    onHover?.(null);
  });

  dom.addEventListener("pointerdown", (event) => {
    downAt = { x: event.clientX, y: event.clientY };
  });

  dom.addEventListener("pointerup", (event) => {
    if (!downAt) return;
    const moved = Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y);
    downAt = null;
    if (moved > CLICK_SLOP_PX) return; // that was an orbit/pan

    const found = pick(event);
    placeMarker(selection, found);
    onSelect?.(found);
  });

  return {
    /** Called by main.js after a rebuild, so stale outlines don't linger. */
    clear() {
      hovered = null;
      highlight.visible = false;
      selection.visible = false;
    },
    /** Re-anchor the selection outline after citizens move (Phase 7). */
    reanchor(found) {
      placeMarker(selection, found);
    },
    selectionMarker: selection,
  };
}

/**
 * Resolve one raycast intersection into `{ kind, record }`.
 *
 * Three cases:
 *   1. the citizens InstancedMesh   -> index into the citizen record array
 *   2. any other InstancedMesh with `userData.records` -> same, for buildings
 *   3. a plain Mesh or a landmark child -> walk up until something carries
 *      `userData.kind` + `userData.record`
 */
function resolveHit(hit, layer) {
  const obj = hit.object;

  if (layer.pick.citizens && obj === layer.pick.citizens.mesh) {
    const record = layer.pick.citizens.records[hit.instanceId];
    return record ? { kind: "citizen", record, point: hit.point } : null;
  }

  if (obj.isInstancedMesh && Array.isArray(obj.userData.records)) {
    const record = obj.userData.records[hit.instanceId];
    return record ? { kind: "building", record, point: hit.point } : null;
  }

  let cursor = obj;
  while (cursor) {
    const data = cursor.userData;
    if (data && data.kind && data.record) {
      return { kind: data.kind, record: data.record, point: hit.point };
    }
    cursor = cursor.parent;
  }
  return null;
}

// ------------------------------------------------------------- highlighting

/**
 * ONE reusable outline box, moved and scaled to whatever is picked.
 *
 * Deliberately not "swap the material of the hovered object": that doesn't work
 * for InstancedMesh (a house shares its material with 999 others) and it forces
 * a material change every hover. A single moving wireframe is one object for the
 * whole map and behaves identically for meshes and instances.
 */
function createHighlight(stage) {
  return addOutline(stage, 0x2a2f3a, 0.75);
}

function createSelection(stage) {
  return addOutline(stage, 0x5b8def, 1);
}

function addOutline(stage, color, opacity) {
  const box = new THREE.BoxGeometry(1, 1, 1);
  box.translate(0, 0.5, 0);
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(box),
    new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity })
  );
  outline.visible = false;
  // Never pickable, never fogged out — it's UI, not scenery.
  outline.userData.isOutline = true;
  stage.scene.add(outline);
  return outline;
}

/**
 * Size the outline to fit whatever kind of thing was picked. The padding values
 * are per-kind because a citizen marker is ~5 units tall and a city plate is
 * ~340 units across — one universal padding would either swallow the citizen or
 * be invisible on the city.
 */
function placeMarker(outline, found) {
  if (!found) {
    outline.visible = false;
    return;
  }

  const r = found.record;
  if (found.kind === "citizen") {
    outline.position.set(r.marker_x, 0.4, r.marker_z);
    outline.scale.set(5, 8, 5);
  } else if (found.kind === "building") {
    outline.position.set(r.world_x, 0.4, r.world_z);
    outline.rotation.y = r.rotation || 0;
    outline.scale.set(r.width * 1.22, r.height * 1.12, r.depth * 1.22);
  } else if (found.kind === "district") {
    outline.position.set(r.world_x, 0.5, r.world_z);
    outline.rotation.y = 0;
    outline.scale.set(r.width, 1, r.depth);
  } else if (found.kind === "city") {
    outline.position.set(r.world_x, 0.6, r.world_z);
    outline.rotation.y = 0;
    // A box around a circular plate: 2r on each side is the bounding square.
    outline.scale.set(r.radius * 2, 1, r.radius * 2);
  } else {
    outline.visible = false;
    return;
  }
  outline.visible = true;
}

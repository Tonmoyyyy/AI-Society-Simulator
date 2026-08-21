/**
 * Every mesh that comes from data: city plates, district plates, roads,
 * buildings, landmarks and citizen markers.
 * (World Phases 3, 4 and 5.)
 *
 * -------------------------------------------------------------------------
 * PERFORMANCE MODEL — why this file looks the way it does (§19)
 * -------------------------------------------------------------------------
 * A 1,000-citizen world is roughly 1,000 houses + 1,000 markers + a few
 * hundred other buildings. Drawn as individual Meshes that would be ~2,300
 * draw calls per frame, which stutters on integrated graphics. So:
 *
 *   * HOUSES  -> ONE InstancedMesh. All houses share one BoxGeometry and one
 *                material; per-house size/rotation live in the instance matrix
 *                and per-house tint in an instanceColor buffer. 1 draw call.
 *   * ROOFS   -> ONE InstancedMesh of cones, same trick. 1 draw call.
 *   * CITIZENS-> ONE InstancedMesh of a low-poly capsule-ish shape. 1 draw
 *                call, and moving them each tick is a matrix write, not a
 *                rebuild.
 *   * OTHER BUILDINGS -> merged per type into one InstancedMesh per type
 *                (shops, factories, offices...). Under a dozen draw calls.
 *   * LANDMARKS -> real individual Meshes, because there are ~6 of them and
 *                they are the whole point of the map (§12).
 *
 * Nothing here creates a DOM element per citizen; labels are CSS2D and are
 * used only for cities and landmarks.
 */

import { THREE, CSS2DObject } from "./scene.js";

// Y offsets — small, deliberate layering so coplanar flat surfaces never
// z-fight. Ground is 0, city plate is 0.10, district plate 0.22, roads 0.34.
const Y_CITY = 0.1;
const Y_DISTRICT = 0.22;
const Y_ROAD = 0.34;

const CITY_PLATE_COLOR = 0xb9c5a8;
const CITY_PLATE_CAPITAL_COLOR = 0xc8c39f;

// A citizen marker's height and radius in world units. Kept chunky enough to
// be visible from the default camera height without a per-marker sprite.
const MARKER_HEIGHT = 5.2;
const MARKER_RADIUS = 1.15;

// Mood is 0..100 from the backend; these are the two ends of the marker colour
// ramp. Green = content, red = unhappy — the "living heatmap" read (§17).
const MOOD_LOW = new THREE.Color("#e2685f");
const MOOD_HIGH = new THREE.Color("#3fbf88");
const MARKER_WORKING = new THREE.Color("#f5a623");

/** Reusable scratch objects — allocating these per instance would churn GC. */
const _m4 = new THREE.Matrix4();
const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _euler = new THREE.Euler();
const _color = new THREE.Color();

export function createWorldLayer(stage) {
  const root = new THREE.Group();
  root.name = "world";
  stage.scene.add(root);

  const layer = {
    root,
    // Groups so a rebuild can dispose one category without touching the rest.
    groups: {
      cities: new THREE.Group(),
      districts: new THREE.Group(),
      roads: new THREE.Group(),
      buildings: new THREE.Group(),
      landmarks: new THREE.Group(),
      citizens: new THREE.Group(),
      labels: new THREE.Group(),
    },
    // Lookup tables the picker uses to turn a hit into a domain object.
    pick: {
      cities: [],       // Mesh[] with userData.record
      districts: [],
      buildings: [],    // includes landmark meshes
      instanced: [],    // { mesh, records } for InstancedMesh hit resolution
      citizens: null,   // { mesh, records }
    },
    citizenRecords: [],
    citizenMesh: null,
    // Landmark groups with a flag or glow ring — the render loop animates only
    // these, so nothing else pays for the per-frame work.
    animated: [],
  };

  Object.values(layer.groups).forEach((g) => root.add(g));

  layer.build = (data, legend) => buildWorld(layer, stage, data, legend);
  layer.updateCitizens = (citizens) => updateCitizens(layer, citizens);
  layer.dispose = () => disposeAll(layer);
  return layer;
}

// ---------------------------------------------------------------- disposal

/**
 * Three.js does not garbage-collect GPU resources, so every rebuild must free
 * the old geometry/material explicitly or the map leaks VRAM each refresh.
 */
function disposeGroup(group) {
  group.traverse((obj) => {
    if (obj.isMesh || obj.isInstancedMesh || obj.isLine) {
      obj.geometry?.dispose?.();
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      mats.forEach((m) => m?.dispose?.());
    }
    if (obj.isCSS2DObject && obj.element?.remove) obj.element.remove();
  });
  group.clear();
}

function disposeAll(layer) {
  Object.values(layer.groups).forEach(disposeGroup);
  layer.pick.cities = [];
  layer.pick.districts = [];
  layer.pick.buildings = [];
  layer.pick.instanced = [];
  layer.pick.citizens = null;
  layer.citizenMesh = null;
  layer.citizenRecords = [];
  layer.animated = [];
}

// ------------------------------------------------------------------- build

function buildWorld(layer, stage, data, legend) {
  disposeAll(layer);

  const districtColors = new Map(
    (legend?.districts || []).map((d) => [d.type, d.color])
  );
  const buildingSpecs = new Map(
    (legend?.buildings || []).map((b) => [b.type, b])
  );

  buildCities(layer, data.cities || []);
  buildDistricts(layer, data.neighborhoods || [], districtColors);
  buildRoads(layer, data.roads || []);
  buildBuildings(layer, data.buildings || [], buildingSpecs, data.government);
  buildCitizenMesh(layer, data.citizens || []);
}

// ---- cities (Phase 3) ----

function buildCities(layer, cities) {
  cities.forEach((city) => {
    // A disc, not a square: cities read as settlements spreading from a centre,
    // and it makes the capital's larger radius immediately legible.
    const geometry = new THREE.CircleGeometry(city.radius, 48);
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshStandardMaterial({
      color: city.is_capital ? CITY_PLATE_CAPITAL_COLOR : CITY_PLATE_COLOR,
      roughness: 0.92,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(city.world_x, Y_CITY, city.world_z);
    mesh.receiveShadow = true;
    mesh.userData = { kind: "city", record: city };
    layer.groups.cities.add(mesh);
    layer.pick.cities.push(mesh);

    // A thin ring border so adjacent city plates stay distinguishable against
    // the green ground.
    const ringGeom = new THREE.RingGeometry(city.radius - 1.6, city.radius, 48);
    ringGeom.rotateX(-Math.PI / 2);
    const ring = new THREE.Mesh(
      ringGeom,
      new THREE.MeshBasicMaterial({
        color: city.is_capital ? 0x9a8b4f : 0x7d8a72,
        transparent: true,
        opacity: 0.6,
        side: THREE.DoubleSide,
      })
    );
    ring.position.set(city.world_x, Y_CITY + 0.02, city.world_z);
    layer.groups.cities.add(ring);

    layer.groups.labels.add(
      makeLabel(
        city.is_capital ? `\u{1F451} ${city.name}` : city.name,
        city.world_x,
        26,
        city.world_z,
        city.is_capital ? "world-label world-label-capital" : "world-label world-label-city"
      )
    );
  });
}

// ---- districts (Phase 3) ----

function buildDistricts(layer, districts, districtColors) {
  districts.forEach((district) => {
    const geometry = new THREE.PlaneGeometry(district.width, district.depth);
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshStandardMaterial({
      // Colour comes from the backend legend, never from a local palette.
      color: new THREE.Color(districtColors.get(district.type) || "#c3c8bd"),
      roughness: 0.9,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(district.world_x, Y_DISTRICT, district.world_z);
    mesh.receiveShadow = true;
    mesh.userData = { kind: "district", record: district };
    layer.groups.districts.add(mesh);
    layer.pick.districts.push(mesh);
  });
}

// ---- roads (Phase 3) ----

function buildRoads(layer, roads) {
  roads.forEach((road) => {
    const dx = road.end_x - road.start_x;
    const dz = road.end_z - road.start_z;
    const length = Math.hypot(dx, dz);
    if (length < 0.5) return;

    // A road is a flat ribbon: one plane, scaled to the segment's length and
    // rotated to its bearing. No curves, no pathfinding — §18 explicitly asks
    // for the simple version first.
    const geometry = new THREE.PlaneGeometry(road.width, length);
    geometry.rotateX(-Math.PI / 2);
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        color: new THREE.Color(road.color),
        roughness: 0.85,
      })
    );
    mesh.position.set(
      (road.start_x + road.end_x) / 2,
      Y_ROAD,
      (road.start_z + road.end_z) / 2
    );
    // atan2(dx, dz) (not dz, dx) because the plane's long axis is +Z after the
    // rotateX above, and we rotate about Y.
    mesh.rotation.y = Math.atan2(dx, dz);
    mesh.userData = { kind: "road", record: road };
    layer.groups.roads.add(mesh);
  });
}

// ---- buildings (Phase 4) + landmarks (Phase 5) ----

function buildBuildings(layer, buildings, buildingSpecs, government) {
  const instancedByType = new Map();
  const landmarks = [];

  buildings.forEach((b) => {
    if (b.is_landmark) landmarks.push(b);
    else {
      if (!instancedByType.has(b.type)) instancedByType.set(b.type, []);
      instancedByType.get(b.type).push(b);
    }
  });

  // Generic buildings: one InstancedMesh per type.
  instancedByType.forEach((records, type) => {
    const spec = buildingSpecs.get(type);
    const color = new THREE.Color(records[0].color || spec?.color || "#cccccc");
    const mesh = buildBoxInstances(records, color);
    mesh.userData = { kind: "buildingInstances", type, records };
    layer.groups.buildings.add(mesh);
    layer.pick.instanced.push({ mesh, records, kind: "building" });

    // Houses additionally get a roof layer, which is what stops a residential
    // district from looking like a car park.
    if (type === "house") {
      const roofs = buildRoofInstances(records);
      // Roof instance i belongs to records[i], so giving the roof mesh the same
      // records array makes a click on a roof resolve to that house. Without
      // this, picking would depend on the ray punching through the roof to the
      // box underneath — which works, but fails at grazing camera angles.
      roofs.userData = { kind: "buildingInstances", type, records };
      layer.groups.buildings.add(roofs);
      layer.pick.instanced.push({ mesh: roofs, records, kind: "building" });
    }
  });

  // Landmarks get bespoke geometry.
  landmarks.forEach((b) => {
    const mesh = buildLandmark(b);
    // Object.assign, NOT a fresh object: buildLandmark already stored the flag,
    // glow ring and pick proxy in userData and overwriting it would silently
    // break the palace animation.
    Object.assign(mesh.userData, { kind: "building", record: b });
    layer.groups.landmarks.add(mesh);
    layer.pick.buildings.push(mesh);
    if (mesh.userData.flag || mesh.userData.glowRing) layer.animated.push(mesh);

    const labelText = landmarkLabel(b, government);
    layer.groups.labels.add(
      makeLabel(
        `${b.icon} ${labelText}`,
        b.world_x,
        b.height + 16,
        b.world_z,
        "world-label world-label-landmark"
      )
    );
  });
}

/**
 * Label text for a landmark.
 *
 * The Presidential Palace shows the sitting President's name when the
 * Government system reports one. That name is read from
 * GET /api/v1/world/government at load time — it is never hardcoded here — so
 * renaming the President from "Tonmoy" to "Alex" changes this label with no
 * frontend change, which is the requirement in §5.
 */
function landmarkLabel(building, government) {
  const base = building.name || building.label;
  if (!government || !government.system_available) return base;
  if (building.type === "presidential_palace" && government.president_name) {
    return `${base} — ${government.president_name}`;
  }
  return base;
}

function buildBoxInstances(records, baseColor) {
  // Unit box centred on the origin, then lifted so its base sits at y=0 —
  // translating the geometry once is cheaper than offsetting every instance.
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  geometry.translate(0, 0.5, 0);

  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.72,
    metalness: 0.02,
  });
  // NOTE: `vertexColors` is deliberately NOT set. InstancedMesh.setColorAt
  // creates an `instanceColor` buffer and Three.js enables the per-instance
  // tint path automatically when it exists; turning on vertexColors as well
  // would make the renderer look for a per-VERTEX colour attribute that this
  // geometry doesn't have.

  const mesh = new THREE.InstancedMesh(geometry, material, records.length);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);

  records.forEach((b, i) => {
    _pos.set(b.world_x, Y_DISTRICT + 0.02, b.world_z);
    _euler.set(0, b.rotation || 0, 0);
    _quat.setFromEuler(_euler);
    _scale.set(b.width, b.height, b.depth);
    _m4.compose(_pos, _quat, _scale);
    mesh.setMatrixAt(i, _m4);

    // Slight per-instance brightness variation. Without it a hundred identical
    // houses look like a texture rather than a neighbourhood.
    const shade = 0.86 + ((b.id * 37) % 100) / 100 * 0.28;
    // Reuse the scratch colour — `new THREE.Color()` per house would be a
    // thousand throwaway allocations on every world load.
    if (b.color) _color.set(b.color);
    else _color.copy(baseColor);
    _color.multiplyScalar(shade);
    mesh.setColorAt(i, _color);
  });

  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.computeBoundingSphere();
  return mesh;
}

function buildRoofInstances(records) {
  // 4-sided cone = a pyramid roof. Rotated 45° so its faces align with the
  // box below it.
  const geometry = new THREE.ConeGeometry(0.72, 1, 4);
  geometry.rotateY(Math.PI / 4);
  geometry.translate(0, 0.5, 0);

  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.8,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, records.length);
  mesh.castShadow = true;

  const roofBase = new THREE.Color("#b4695c");
  records.forEach((b, i) => {
    const roofHeight = b.height * 0.42;
    _pos.set(b.world_x, Y_DISTRICT + 0.02 + b.height, b.world_z);
    _euler.set(0, b.rotation || 0, 0);
    _quat.setFromEuler(_euler);
    _scale.set(b.width * 1.5, roofHeight, b.depth * 1.5);
    _m4.compose(_pos, _quat, _scale);
    mesh.setMatrixAt(i, _m4);

    const shade = 0.82 + ((b.id * 53) % 100) / 100 * 0.34;
    _color.copy(roofBase).multiplyScalar(shade);
    mesh.setColorAt(i, _color);
  });

  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.computeBoundingSphere();
  return mesh;
}

// ---- landmark geometry (Phase 5) ----

/**
 * Landmarks are the only buildings built as real Meshes with multiple parts.
 * There are about six in the whole world, so the extra draw calls are free —
 * and they are what makes the capital read as a seat of government rather than
 * a slightly larger office block (§12).
 *
 * Each landmark is a Group. It carries `kind`/`record` in its own userData and
 * the picker walks up from whichever child part was hit, so no invisible
 * click-proxy box is needed — one less object per landmark, and no reliance on
 * how a given Three.js version treats `visible: false` during raycasts.
 */
function buildLandmark(b) {
  const group = new THREE.Group();
  group.position.set(b.world_x, Y_DISTRICT + 0.02, b.world_z);
  group.rotation.y = b.rotation || 0;

  const stone = new THREE.MeshStandardMaterial({
    color: new THREE.Color(b.color),
    roughness: 0.62,
    metalness: 0.04,
  });
  const trim = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#c9a227"),
    roughness: 0.35,
    metalness: 0.55,
  });

  if (b.type === "monument") {
    buildMonument(group, b, stone, trim);
  } else {
    buildCivicBuilding(group, b, stone, trim, b.type === "presidential_palace");
  }

  return group;
}

function buildCivicBuilding(group, b, stone, trim, isPalace) {
  const bodyHeight = b.height * 0.62;

  // Stepped plinth — the classic civic silhouette, and it grounds the building
  // on the district plate instead of letting it float.
  const plinth = new THREE.Mesh(
    new THREE.BoxGeometry(b.width * 1.12, b.height * 0.07, b.depth * 1.16),
    stone
  );
  plinth.position.y = b.height * 0.035;
  plinth.castShadow = true;
  plinth.receiveShadow = true;
  group.add(plinth);

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(b.width, bodyHeight, b.depth),
    stone
  );
  body.position.y = b.height * 0.07 + bodyHeight / 2;
  body.castShadow = true;
  body.receiveShadow = true;
  group.add(body);

  // Colonnade across the front face.
  const columnCount = isPalace ? 8 : 6;
  const columnGeom = new THREE.CylinderGeometry(
    b.width * 0.022,
    b.width * 0.026,
    bodyHeight * 0.86,
    10
  );
  const columns = new THREE.InstancedMesh(columnGeom, stone, columnCount);
  columns.castShadow = true;
  const span = b.width * 0.78;
  for (let i = 0; i < columnCount; i += 1) {
    const t = columnCount === 1 ? 0.5 : i / (columnCount - 1);
    _pos.set(
      -span / 2 + span * t,
      b.height * 0.07 + (bodyHeight * 0.86) / 2,
      b.depth / 2 + b.depth * 0.06
    );
    _quat.identity();
    _scale.set(1, 1, 1);
    _m4.compose(_pos, _quat, _scale);
    columns.setMatrixAt(i, _m4);
  }
  columns.instanceMatrix.needsUpdate = true;
  group.add(columns);

  // Portico roof over the columns.
  const portico = new THREE.Mesh(
    new THREE.BoxGeometry(b.width * 0.86, b.height * 0.05, b.depth * 0.18),
    stone
  );
  portico.position.set(
    0,
    b.height * 0.07 + bodyHeight * 0.88,
    b.depth / 2 + b.depth * 0.06
  );
  portico.castShadow = true;
  group.add(portico);

  // Dome + flag: the actual signature of the palace/parliament.
  const domeRadius = Math.min(b.width, b.depth) * 0.3;
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(domeRadius, 26, 14, 0, Math.PI * 2, 0, Math.PI / 2),
    isPalace ? trim : stone
  );
  dome.position.y = b.height * 0.07 + bodyHeight;
  dome.castShadow = true;
  group.add(dome);

  const drum = new THREE.Mesh(
    new THREE.CylinderGeometry(domeRadius * 1.05, domeRadius * 1.1, b.height * 0.08, 22),
    stone
  );
  drum.position.y = b.height * 0.07 + bodyHeight - b.height * 0.03;
  drum.castShadow = true;
  group.add(drum);

  const mast = new THREE.Mesh(
    new THREE.CylinderGeometry(0.28, 0.28, b.height * 0.3, 6),
    trim
  );
  mast.position.y = b.height * 0.07 + bodyHeight + domeRadius + b.height * 0.15;
  group.add(mast);

  const flag = new THREE.Mesh(
    new THREE.PlaneGeometry(b.width * 0.12, b.height * 0.07),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color("#3f9f6f"),
      side: THREE.DoubleSide,
      roughness: 0.9,
    })
  );
  flag.position.set(
    b.width * 0.06,
    b.height * 0.07 + bodyHeight + domeRadius + b.height * 0.26,
    0
  );
  group.add(flag);
  // Animated by the render loop — a tiny bit of motion is what tells you the
  // simulation is live even when no citizen happens to be moving.
  group.userData.flag = flag;

  if (isPalace) {
    // Warm spotlight + glow ring so the palace is findable from any camera
    // height without needing a minimap.
    const spot = new THREE.SpotLight(0xffe6ad, 2.4, 260, Math.PI / 6, 0.45, 1.2);
    spot.position.set(0, b.height * 2.4, b.depth * 1.1);
    spot.target = body;
    group.add(spot);
    group.add(spot.target);

    const ringGeom = new THREE.RingGeometry(b.width * 0.78, b.width * 0.92, 44);
    ringGeom.rotateX(-Math.PI / 2);
    const ring = new THREE.Mesh(
      ringGeom,
      new THREE.MeshBasicMaterial({
        color: 0xf2d17a,
        transparent: true,
        opacity: 0.5,
        side: THREE.DoubleSide,
      })
    );
    ring.position.y = 0.16;
    group.add(ring);
    group.userData.glowRing = ring;
  }
}

function buildMonument(group, b, stone, trim) {
  const base = new THREE.Mesh(
    new THREE.BoxGeometry(b.width * 1.4, b.height * 0.1, b.depth * 1.4),
    stone
  );
  base.position.y = b.height * 0.05;
  base.castShadow = true;
  base.receiveShadow = true;
  group.add(base);

  // A tapered obelisk — cheap, unmistakable, and reads at any zoom.
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(b.width * 0.1, b.width * 0.22, b.height * 0.78, 4),
    stone
  );
  shaft.rotation.y = Math.PI / 4;
  shaft.position.y = b.height * 0.1 + (b.height * 0.78) / 2;
  shaft.castShadow = true;
  group.add(shaft);

  const cap = new THREE.Mesh(
    new THREE.ConeGeometry(b.width * 0.13, b.height * 0.14, 4),
    trim
  );
  cap.rotation.y = Math.PI / 4;
  cap.position.y = b.height * 0.1 + b.height * 0.78 + b.height * 0.07;
  cap.castShadow = true;
  group.add(cap);
}

// ---- citizens (Phase 4 + Phase 7) ----

/**
 * One InstancedMesh for every citizen in the world.
 *
 * Allocated with headroom (`capacity`) so that a tick which adds a few citizens
 * only writes matrices instead of reallocating the buffer — reallocating would
 * mean a new GPU upload and a visible hitch.
 */
function buildCitizenMesh(layer, citizens) {
  const capacity = Math.max(64, Math.ceil((citizens.length + 24) / 64) * 64);

  // Cylinder + sphere would be two draw calls; a single tapered cylinder with a
  // rounded look is enough at this scale. (CapsuleGeometry is avoided on
  // purpose — it doesn't exist in older Three.js builds.)
  const geometry = new THREE.CylinderGeometry(
    MARKER_RADIUS * 0.72,
    MARKER_RADIUS,
    MARKER_HEIGHT,
    8,
    1
  );
  geometry.translate(0, MARKER_HEIGHT / 2, 0);

  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.45,
    metalness: 0.05,
  });

  const mesh = new THREE.InstancedMesh(geometry, material, capacity);
  mesh.castShadow = false; // 1,000 shadow casters is not worth the frame time
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.count = 0;
  mesh.frustumCulled = false; // count changes every tick; let us manage it
  mesh.name = "citizens";

  layer.groups.citizens.add(mesh);
  layer.citizenMesh = mesh;
  layer.pick.citizens = { mesh, records: [] };

  updateCitizens(layer, citizens);
}

/**
 * Move every citizen marker to its current position.
 *
 * Called on first build and again on every refresh (Phase 7). Writes matrices
 * and colours in place; only reallocates when the population outgrows the
 * buffer, which is what makes a tick refresh cheap.
 */
function updateCitizens(layer, citizens) {
  let mesh = layer.citizenMesh;
  if (!mesh) return;

  // instanceMatrix.count is the allocated capacity (not the drawn count), so
  // this is the real "did we outgrow the buffer" test.
  if (citizens.length > mesh.instanceMatrix.count) {
    disposeGroup(layer.groups.citizens);
    layer.citizenMesh = null;
    buildCitizenMesh(layer, citizens);
    return;
  }

  mesh.count = citizens.length;
  layer.citizenRecords = citizens;
  layer.pick.citizens = { mesh, records: citizens };

  citizens.forEach((c, i) => {
    _pos.set(c.marker_x, Y_DISTRICT + 0.02, c.marker_z);
    _quat.identity();
    // Taller when working, so a busy commercial district visibly differs from a
    // sleeping residential one even before you read any label.
    _scale.set(1, c.at_work ? 1.16 : 1, 1);
    _m4.compose(_pos, _quat, _scale);
    mesh.setMatrixAt(i, _m4);

    const mood = Math.max(0, Math.min(100, c.mood ?? 50)) / 100;
    _color.copy(MOOD_LOW).lerp(MOOD_HIGH, mood);
    if (c.at_work) _color.lerp(MARKER_WORKING, 0.35);
    mesh.setColorAt(i, _color);
  });

  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  // MUST be recomputed after moving instances: InstancedMesh.raycast rejects the
  // whole mesh against a cached bounding sphere, so a stale sphere would make
  // citizens silently unclickable once they walked away from their homes.
  mesh.computeBoundingSphere();
}

// ------------------------------------------------------------------ labels

function makeLabel(text, x, y, z, className) {
  const el = document.createElement("div");
  el.className = className;
  el.textContent = text;
  const label = new CSS2DObject(el);
  label.position.set(x, y, z);
  // Hidden beyond this distance by the render loop (Phase 8) — otherwise every
  // city name in the world stays legible at max zoom-out and it's a mess.
  label.userData.maxDistance = className.includes("landmark") ? 700 : 2600;
  return label;
}

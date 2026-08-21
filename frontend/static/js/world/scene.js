/**
 * The Three.js stage: renderer, camera, controls, lights, sky and ground
 * (World Phase 3).
 *
 * Deliberately knows NOTHING about cities, citizens or the API — it only owns
 * the things that exist before any data arrives. Everything data-driven lives in
 * builders.js. That split is what keeps a reload of the world from having to
 * tear down and rebuild the renderer.
 *
 * COORDINATE CONVENTION (this is the one thing to remember)
 * ---------------------------------------------------------
 * Three.js is Y-up, so the ground is the XZ plane:
 *     backend world_x  ->  THREE x
 *     backend world_z  ->  THREE z
 *     height           ->  THREE y
 * The backend stores X/Z (never X/Y) for exactly this reason, so no axis
 * swapping happens anywhere in the frontend.
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

export { THREE, CSS2DObject };

// Sky/fog tuned to the app's light "premium glass" palette rather than a
// game-like blue, because the map sits inside the same UI as the dashboard.
const SKY_COLOR = 0xdfe7f5;
const FOG_NEAR = 900;
const FOG_FAR = 3200;

// The ground is one big plate, not a heightmap: §7 asks for a clean stylized
// civilization seen from above, and flat terrain keeps 1,000 citizens cheap.
const GROUND_SIZE = 4200;
const GROUND_COLOR = 0x9fc79a;

/**
 * Cap the device pixel ratio. On a 3x-DPR laptop screen an uncapped ratio
 * renders ~9x the pixels for a barely visible gain and is the single biggest
 * frame-rate cost in a scene like this (Phase 8).
 */
const MAX_PIXEL_RATIO = 1.75;

export function createStage(canvasHost, labelHost) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SKY_COLOR);
  // Fog does double duty: it sells the "observed from above" scale AND hides
  // the edge of the ground plate, so we never need a bigger plate.
  scene.fog = new THREE.Fog(SKY_COLOR, FOG_NEAR, FOG_FAR);

  const camera = new THREE.PerspectiveCamera(
    45,
    canvasHost.clientWidth / Math.max(canvasHost.clientHeight, 1),
    1,
    6000
  );
  // Starting pose: high, tilted, looking at the origin — the capital sits at
  // (0,0) by design, so the president's city is what you see first.
  camera.position.set(360, 460, 620);

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO));
  renderer.setSize(canvasHost.clientWidth, canvasHost.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  canvasHost.appendChild(renderer.domElement);

  // CSS2DRenderer draws labels as real DOM nodes positioned in 3D. Used ONLY
  // for a handful of landmarks and city names — never per citizen. §19 warns
  // against a DOM element per citizen and it is right: 1,000 divs would stall
  // layout every frame. Citizens are InstancedMesh points instead.
  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(canvasHost.clientWidth, canvasHost.clientHeight);
  labelRenderer.domElement.className = "world-labels";
  labelHost.appendChild(labelRenderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.screenSpacePanning = false;
  controls.minDistance = 40;
  controls.maxDistance = 2400;
  // Never let the camera go under the ground: this is an observation tool, not
  // a first-person game (§20 — the user is an administrator, not a player).
  controls.maxPolarAngle = Math.PI * 0.475;
  controls.target.set(0, 0, 0);

  addLights(scene);
  const ground = addGround(scene);

  return { scene, camera, renderer, labelRenderer, controls, ground };
}

function addLights(scene) {
  // Hemisphere light = soft sky/ground bounce. Doing the ambient fill this way
  // (instead of a flat AmbientLight) is what makes untextured low-poly boxes
  // read as buildings rather than as flat silhouettes.
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8fae86, 0.85));

  const sun = new THREE.DirectionalLight(0xfff6e2, 1.15);
  sun.position.set(-520, 780, 420);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);

  // Shadow camera framing is a budget decision: one 2048 map stretched over the
  // whole 4,200-unit world would give mushy shadows, so it covers the populated
  // core and distant cities simply render unshadowed.
  const d = 900;
  sun.shadow.camera.left = -d;
  sun.shadow.camera.right = d;
  sun.shadow.camera.top = d;
  sun.shadow.camera.bottom = -d;
  sun.shadow.camera.near = 10;
  sun.shadow.camera.far = 2600;
  sun.shadow.bias = -0.0006;
  sun.shadow.normalBias = 0.9;
  scene.add(sun);
  scene.userData.sun = sun;

  // A dim fill from the opposite side so north-facing walls aren't pure black.
  const fill = new THREE.DirectionalLight(0xc8d8ff, 0.28);
  fill.position.set(480, 300, -520);
  scene.add(fill);
}

function addGround(scene) {
  const geometry = new THREE.PlaneGeometry(GROUND_SIZE, GROUND_SIZE, 1, 1);
  // A PlaneGeometry is born in the XY plane facing +Z; rotating -90° about X
  // lays it flat as the XZ ground.
  geometry.rotateX(-Math.PI / 2);

  const material = new THREE.MeshStandardMaterial({
    color: GROUND_COLOR,
    roughness: 0.95,
    metalness: 0.0,
  });

  const ground = new THREE.Mesh(geometry, material);
  ground.receiveShadow = true;
  ground.name = "ground";
  // Rendered first so the flat district plates layered just above it never
  // z-fight with it.
  ground.renderOrder = -1;
  scene.add(ground);
  return ground;
}

/**
 * Resize handling. Called from a ResizeObserver in main.js rather than a
 * window 'resize' listener, so opening the side panel (which changes the
 * canvas width without changing the window size) also re-frames correctly.
 */
export function resizeStage(stage, width, height) {
  if (width <= 0 || height <= 0) return;
  stage.camera.aspect = width / height;
  stage.camera.updateProjectionMatrix();
  stage.renderer.setSize(width, height);
  stage.labelRenderer.setSize(width, height);
}

/**
 * Fly the camera to a point over `frames` frames.
 *
 * Hand-rolled easing instead of a tween library: it's ~15 lines, and adding a
 * dependency for it would work against "keep this project manageable for a
 * solo developer" (§22).
 */
export function flyTo(stage, target, distance, frames = 46) {
  const startTarget = stage.controls.target.clone();
  const startPos = stage.camera.position.clone();

  const endTarget = new THREE.Vector3(target.x, 0, target.z);
  // Approach from the same direction the camera is already looking, so the
  // view never spins disorientingly when you pick a city from the dropdown.
  const dir = startPos.clone().sub(startTarget).normalize();
  const endPos = endTarget.clone().add(dir.multiplyScalar(distance));
  endPos.y = Math.max(endPos.y, distance * 0.42);

  let frame = 0;
  stage.flight = () => {
    frame += 1;
    const t = Math.min(frame / frames, 1);
    // easeInOutCubic
    const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    stage.controls.target.lerpVectors(startTarget, endTarget, e);
    stage.camera.position.lerpVectors(startPos, endPos, e);
    if (t >= 1) stage.flight = null;
  };
}

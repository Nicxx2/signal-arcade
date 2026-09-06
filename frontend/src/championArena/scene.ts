import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { ArenaView, Fighter, Quality } from "./model";
import { EMBLEMS, VISORS, familyMark } from "./design";
import type { Segment } from "./design";
import { movePlan, sampleMotion } from "./motion";
import type { Motion, MovePlan } from "./motion";
import { DPR, FPS, QualityGovernor } from "./performance";
import type { Tier } from "./performance";

export interface SceneReport { viewKey: string; tier: Tier; calls: number; triangles: number; geometries: number; textures: number }
export interface ArenaScene { setView: (view: ArenaView) => void; setActive: (active: boolean) => void; setQuality: (quality: Quality) => void; replay: () => void; finish: () => void; dispose: () => void }
type Rig = { root: THREE.Group; torso: THREE.Group; head: THREE.Group; crown: THREE.Group; arms: THREE.Group[]; forearms: THREE.Group[]; legs: THREE.Group[]; x: number; direction: number; fighter: Fighter; moves: MovePlan };

/** Original segmented robot rigs and arena. This module is the sole 3D import boundary. */
export function createArenaScene(host: HTMLElement, initial: ArenaView, preference: Quality, report: (report: SceneReport) => void, failure: (message: string) => void): ArenaScene {
  let disposed = false;
  let active = false;
  let frame = 0;
  let elapsed = 0;
  let lastTick = 0;
  let lastDraw = 0;
  let motion: Motion = initial.replayFinal === false ? "exchange" : initial.mode === "recap" ? "recap" : "intro";
  let duration = motion === "recap" ? 5.8 : motion === "exchange" ? 1.6 : 3.2;
  let view = initial;
  const checkpoint = () => String(view.replayAt ?? view.replayStep ?? view.usable ?? "profile");
  let lastCount = initial.usable;
  const governor = new QualityGovernor(preference);
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const fighterGeometries = new Set<THREE.BufferGeometry>();
  const fighterMaterials = new Set<THREE.Material>();
  let buildingFighters = false;
  const scene = new THREE.Scene();
  const content = new THREE.Group(); scene.add(content);
  let edgeMaterial: THREE.MeshPhongMaterial | null = null;
  const camera = new THREE.PerspectiveCamera(36, 1, .1, 60);
  let renderer: THREE.WebGLRenderer | null = null;
  let observer: ResizeObserver | null = null;
  let rigs: Rig[] = [];
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.dataset.championRenderer = "true";

  const geo = <T extends THREE.BufferGeometry>(value: T): T => { geometries.add(value); if (buildingFighters) fighterGeometries.add(value); return value; };
  const mat = <T extends THREE.Material>(value: T): T => { materials.add(value); if (buildingFighters) fighterMaterials.add(value); return value; };
  // Explicit lights need no PBR lookup texture. Three r185's shared DFG_LUT retains a
  // dispose listener for each closed renderer; Phong avoids that global texture entirely.
  const lit = (color: THREE.ColorRepresentation, sheen = .45, emissive?: string) => mat(new THREE.MeshPhongMaterial({ color, specular: "#688295", shininess: 20 + sheen * 60, ...(emissive ? { emissive, emissiveIntensity: .5 } : {}) }));
  const cube = geo(new THREE.BoxGeometry(1, 1, 1));
  const joint = geo(new THREE.IcosahedronGeometry(1, 1));
  const cylinder = geo(new THREE.CylinderGeometry(1, 1, 1, 8));
  const armour = geo(new THREE.IcosahedronGeometry(1, 0));
  const plateShape = new THREE.Shape([new THREE.Vector2(-.45, .3), new THREE.Vector2(0, .4), new THREE.Vector2(.45, .3), new THREE.Vector2(.36, -.25), new THREE.Vector2(0, -.4), new THREE.Vector2(-.36, -.25)]);
  const plate = geo(new THREE.ExtrudeGeometry(plateShape, { depth: .13, bevelEnabled: true, bevelThickness: .035, bevelSize: .025, bevelSegments: 1, curveSegments: 1 }));
  function mesh(parent: THREE.Object3D, shape: THREE.BufferGeometry, material: THREE.Material, position: [number, number, number], scale: [number, number, number]) {
    const result = new THREE.Mesh(shape, material); result.position.set(...position); result.scale.set(...scale); parent.add(result); return result;
  }
  function group(parent: THREE.Object3D, x: number, y: number, z = 0) { const result = new THREE.Group(); result.position.set(x, y, z); parent.add(result); return result; }
  function glyph(parent: THREE.Group, segments: readonly Segment[], material: THREE.Material, x: number, y: number, z: number, sx: number, sy: number, width = .018) {
    for (const [x1, y1, x2, y2] of segments) {
      const dx = (x2 - x1) * sx, dy = (y2 - y1) * sy;
      const line = mesh(parent, cube, material, [x + (x1 + x2) * sx / 2, y + (y1 + y2) * sy / 2, z], [Math.hypot(dx, dy), width, .015]);
      line.rotation.z = Math.atan2(dy, dx);
    }
  }
  // Merge rigid pieces by material inside each joint; articulated children remain independent.
  function consolidate(parent: THREE.Group) {
    parent.children.filter((child): child is THREE.Group => child instanceof THREE.Group).forEach(consolidate);
    const byMaterial = new Map<THREE.Material, THREE.Mesh[]>();
    for (const child of parent.children) {
      if (!(child instanceof THREE.Mesh) || Array.isArray(child.material)) continue;
      const members = byMaterial.get(child.material) ?? []; members.push(child); byMaterial.set(child.material, members);
    }
    for (const [material, members] of byMaterial) {
      if (members.length < 2) continue;
      const transformed = members.map((member) => { member.updateMatrix(); return (member.geometry.index ? member.geometry.toNonIndexed() : member.geometry.clone()).applyMatrix4(member.matrix); });
      const merged = mergeGeometries(transformed);
      transformed.forEach((geometry) => geometry.dispose());
      if (merged) { members.forEach((member) => parent.remove(member)); parent.add(new THREE.Mesh(geo(merged), material)); }
    }
  }
  function fighterRig(fighter: Fighter, x: number, direction: number): Rig {
    const root = group(content, x, .14);
    const bulk = [.9, 1, 1.1][fighter.build] ?? 1;
    root.scale.set(bulk, 1, 1);
    root.rotation.y = direction * .28;
    const body = lit(new THREE.Color("#4b627d").lerp(new THREE.Color(fighter.color), .12));
    const dark = lit("#172438", .5);
    const light = lit(fighter.color, .3, fighter.color);
    const trim = lit(fighter.trim, .3, fighter.trim);
    const torso = group(root, 0, 1.6);
    mesh(torso, armour, body, [0, .15, 0], [.47, .53, .28]);
    mesh(torso, plate, body, [0, .16, .22], [.8, .76, 1]);
    mesh(torso, plate, dark, [0, .18, .36], [.57, .45, .2]);
    glyph(torso, EMBLEMS[fighter.details.emblem]!, light, 0, .17, .42, .21, .15);
    glyph(torso, familyMark(fighter.family), trim, 0, .17, .43, .2, .19, .022);
    if (fighter.details.trim === 1) glyph(torso, [[-.31, .32, -.2, .28], [.2, .28, .31, .32], [-.24, -.04, -.14, -.1], [.14, -.1, .24, -.04]], light, 0, 0, .385, 1, 1);
    if (fighter.details.trim === 2) glyph(torso, [[-.28, .31, -.25, .13], [.28, .31, .25, .13], [-.08, -.14, .08, -.14]], light, 0, 0, .385, 1, 1);
    mesh(torso, cylinder, dark, [0, -.37, 0], [.21, .25, .19]);
    mesh(root, armour, body, [0, 1.04, 0], [.35, .23, .22]);
    mesh(root, cube, light, [0, 1.04, .21], [.22, .035, .035]);
    const head = group(torso, 0, .74);
    mesh(head, cylinder, dark, [0, -.19, 0], [.12, .16, .12]);
    mesh(head, armour, body, [0, .05, 0], [.29, .34, .26]);
    if (fighter.details.helmet === 1) mesh(head, plate, body, [0, .22, .17], [.57, .25, .3]);
    if (fighter.details.helmet === 2) for (const sign of [-1, 1]) { const cheek = mesh(head, cube, light, [sign * .23, -.04, .15], [.04, .22, .12]); cheek.rotation.z = sign * .25; }
    if (fighter.details.helmet === 3) mesh(head, plate, light, [0, .26, .2], [.13, .26, .25]);
    mesh(head, plate, dark, [0, .025, .215], [.52, .33, .18]);
    glyph(head, VISORS[fighter.details.visor]!, light, 0, .05, .285, .23, .14, .035);
    if (fighter.family === "XGBoost") for (const sign of [-1, 1]) glyph(head, [[sign * .4, .1, sign * .4, .29], [sign * .4, .29, sign * .49, .39], [sign * .4, .29, sign * .32, .39]], light, 0, 0, .03, 1, 1, .025);
    mesh(head, cube, body, [0, -.115, .22], [.13, .12, .08]);
    if (fighter.crest === 2) {
      const fin = mesh(head, plate, light, [0, .32, -.03], [.24, .35, .22]); fin.rotation.y = Math.PI / 2;
    } else if (fighter.crest === 1) {
      for (const sign of [-1, 1]) { const fin = mesh(head, armour, body, [sign * .29, .2, -.08], [.09, .28, .16]); fin.rotation.z = -sign * .35; }
    }
    const crown = group(head, 0, .66);
    crown.visible = false;
    if (view.mode === "recap") {
      const gold = lit("#ffd47c", .6, "#a66b20");
      mesh(crown, geo(new THREE.TorusGeometry(.24, .025, 4, 12)), gold, [0, 0, 0], [1, 1, 1]).rotation.x = Math.PI / 2;
      const spike = geo(new THREE.ConeGeometry(.055, .16, 4));
      for (let i = 0; i < 5; i++) { const angle = i * Math.PI * 2 / 5; mesh(crown, spike, gold, [Math.sin(angle) * .24, .075, Math.cos(angle) * .24], [1, 1, 1]); }
    }
    const arms: THREE.Group[] = [], forearms: THREE.Group[] = [], legs: THREE.Group[] = [];
    for (const sign of [-1, 1]) {
      const arm = group(torso, sign * .47, .39);
      mesh(arm, armour, body, [sign * .025, -.015, 0], [fighter.build === 2 ? .28 : .23, .24, .27]);
      if (fighter.details.shoulders === 1) {
        mesh(arm, plate, body, [sign * .03, .015, .20], [.44, .3, .25]);
        glyph(arm, [[-.13, .035, 0, .085], [0, .085, .13, .035]], light, sign * .03, 0, .27, 1, 1);
      } else if (fighter.details.shoulders === 2) {
        const fin = mesh(arm, armour, body, [sign * .1, .16, -.04], [.18, .18, .19]); fin.rotation.z = sign * .45;
      } else if (fighter.details.shoulders === 3) {
        mesh(arm, plate, light, [sign * .025, -.01, .23], [.38, .31, .22]);
        mesh(arm, plate, dark, [sign * .025, -.01, .27], [.29, .23, .15]);
      }
      mesh(arm, cube, light, [sign * .06, .085, .22], [.17, .035, .035]);
      mesh(arm, cylinder, dark, [0, -.27, 0], [.10, .34, .1]);
      const forearm = group(arm, 0, -.46);
      mesh(forearm, joint, dark, [0, 0, 0], [.12, .12, .12]);
      mesh(forearm, armour, body, [0, -.20, 0], [.17, .3, .18]);
      mesh(forearm, cube, light, [0, -.2, .16], [.065, .21, .025]);
      mesh(forearm, cube, dark, [0, -.45, .01], [.20, .18, .21]);
      if (fighter.build === 0 && sign === -1) {
        mesh(forearm, plate, light, [0, -.22, .23], [.52, .69, .3]);
        mesh(forearm, plate, dark, [0, -.22, .3], [.38, .51, .15]);
      }
      arms.push(arm); forearms.push(forearm);
      const leg = group(root, sign * .21, 1.0);
      mesh(leg, cylinder, body, [0, -.22, 0], [.145, .42, .145]);
      mesh(leg, armour, dark, [0, -.43, .045], [.16, .14, .17]);
      mesh(leg, armour, body, [0, -.65, 0], [.16, .33, .17]);
      mesh(leg, cube, light, [0, -.65, .16], [.035, .22, .025]);
      mesh(leg, cube, dark, [0, -.89, .11], [.29, .18, .45]);
      legs.push(leg);
    }
    consolidate(root);
    return { root, torso, head, crown, arms, forearms, legs, x, direction, fighter, moves: movePlan(fighter, view.key, checkpoint()) };
  }
  function buildFighters() {
    // Retain only the shared platform, lights and base shapes. Replaced fighters own their
    // merged geometry/materials and release them before building the newly selected pair.
    content.clear(); rigs = [];
    fighterGeometries.forEach(value => { value.dispose(); geometries.delete(value); });
    fighterMaterials.forEach(value => { value.dispose(); materials.delete(value); });
    fighterGeometries.clear(); fighterMaterials.clear();
    const accent = { entry: "#398b9d", manipulation: "#7d69a4", sizing: "#a58a55", exit: "#58a28a" }[view.skill];
    edgeMaterial?.color.set(accent); edgeMaterial?.emissive.set(accent);
    buildingFighters = true;
    try {
      if (view.left) rigs.push(fighterRig(view.left, view.right ? -1.45 : -.9, 1));
      if (view.right) rigs.push(fighterRig(view.right, 1.45, -1));
      if (!view.right) {
        const target = group(content, 1.25, 1.5);
        const holo = mat(new THREE.MeshBasicMaterial({ color: view.left?.color ?? "#80d9f5", transparent: true, opacity: .32, wireframe: true }));
        mesh(target, geo(new THREE.IcosahedronGeometry(.45, 0)), holo, [0, 0, 0], [1, 1.25, 1]);
      }
    } finally { buildingFighters = false; }
  }
  function resetRig(rig: Rig) {
    rig.root.position.set(rig.x, .14, 0); rig.root.rotation.set(0, rig.direction * .28, 0);
    rig.torso.rotation.set(0, 0, 0); rig.head.rotation.set(0, 0, 0);
    rig.arms.forEach((arm, i) => arm.rotation.set(-.1, 0, i === 0 ? -.12 : .12));
    rig.forearms.forEach((arm) => arm.rotation.set(-.22, 0, 0));
    rig.legs.forEach((leg, i) => leg.rotation.set(0, 0, i === 0 ? -.025 : .025));
  }
  function pose(time: number) {
    for (let i = 0; i < rigs.length; i++) {
      const rig = rigs[i]!;
      resetRig(rig);
      const left = i === 0;
      const sampled = sampleMotion(rig.moves, { motion, time, duration, left, paired: rigs.length > 1, advantage: view.momentum === (left ? "left" : "right"), outcome: view.outcome });
      rig.root.position.x = rig.x + sampled.x;
      rig.root.rotation.y = sampled.yaw;
      rig.torso.position.y = sampled.torsoY;
      rig.torso.rotation.y = sampled.torsoYaw;
      rig.torso.rotation.z = sampled.torsoLean;
      rig.head.rotation.x = sampled.headPitch;
      rig.head.rotation.y = sampled.headYaw;
      rig.crown.visible = sampled.crown;
      for (const index of [0, 1]) {
        rig.arms[index]!.rotation.x = sampled.armX[index]!;
        rig.arms[index]!.rotation.z = sampled.armZ[index]!;
        rig.forearms[index]!.rotation.x = sampled.forearmX[index]!;
      }
    }
  }
  function resize() {
    if (disposed || !renderer) return;
    const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, DPR[governor.tier]));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    const distance = Math.max(view.mode === "recap" ? 7.1 : 6.3, 7.2 / Math.max(.7, camera.aspect));
    camera.position.set(0, 3.0, distance);
    camera.lookAt(0, view.mode === "recap" ? 1.5 : 1.2, 0);
    camera.updateProjectionMatrix();
    draw();
  }
  function emit() { if (renderer && !disposed) report({ viewKey: view.key, tier: governor.tier, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures }); }
  function draw() {
    if (!renderer || disposed) return;
    try { renderer.render(scene, camera); }
    catch { fatal("The graphics renderer stopped. Your evidence remains available in 2D."); }
  }
  function stopFrame() { if (frame) cancelAnimationFrame(frame); frame = 0; lastTick = 0; lastDraw = 0; }
  function fatal(message: string) { dispose(); failure(message); }
  function tick(now: number) {
    frame = 0;
    if (!active || disposed) return;
    if (!lastTick) lastTick = now;
    if (lastDraw && now - lastDraw < 1000 / FPS[governor.tier] - 1) { frame = requestAnimationFrame(tick); return; }
    const interval = lastDraw ? now - lastDraw : 1000 / FPS[governor.tier];
    elapsed = Math.min(duration, elapsed + Math.min(.1, (now - lastTick) / 1000));
    lastTick = now; lastDraw = now;
    const started = performance.now();
    pose(elapsed); draw();
    if (disposed) return;
    const decision = governor.sample(performance.now() - started, interval);
    if (decision === "fallback") { fatal("This device is more comfortable in 2D. All battle information is preserved."); return; }
    if (decision) { resize(); emit(); }
    if (elapsed < duration) frame = requestAnimationFrame(tick);
    else { stopFrame(); emit(); }
  }
  function begin(next: Motion) { rigs.forEach(rig => { rig.moves = movePlan(rig.fighter, view.key, checkpoint()); }); motion = next; elapsed = 0; duration = next === "recap" ? 5.8 : next === "exchange" ? view.replayStep !== undefined ? 1.6 : 2.8 : 3.2; stopFrame(); if (active && !disposed) { pose(0); draw(); frame = requestAnimationFrame(tick); } else { pose(next === "recap" ? duration : 0); draw(); } }
  function lost(event: Event) { event.preventDefault(); fatal("The graphics context was lost. Continue in 2D, or try 3D once more."); }
  function dispose() {
    if (disposed) return;
    disposed = true; active = false; stopFrame(); observer?.disconnect();
    canvas.removeEventListener("webglcontextlost", lost);
    geometries.forEach((geometry) => geometry.dispose()); materials.forEach((material) => material.dispose());
    geometries.clear(); materials.clear(); scene.clear(); rigs = [];
    fighterGeometries.clear(); fighterMaterials.clear(); content.clear();
    renderer?.dispose(); renderer?.forceContextLoss(); renderer = null;
    canvas.width = 0; canvas.height = 0; canvas.remove();
  }
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power" });
    renderer.setClearColor(0x07101d, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    host.appendChild(canvas);
    canvas.addEventListener("webglcontextlost", lost);
    scene.add(new THREE.HemisphereLight(0xc8e2ff, 0x14203c, 2.2));
    const key = new THREE.DirectionalLight(0xeafaff, 3.3); key.position.set(-3, 6, 4); scene.add(key);
    const rim = new THREE.DirectionalLight(0x7d8eff, 2.6); rim.position.set(3, 3, -4); scene.add(rim);
    const platform = group(scene, 0, 0);
    const stageMat = lit("#182c40", .55);
    const stageColor = { entry: "#398b9d", manipulation: "#7d69a4", sizing: "#a58a55", exit: "#58a28a" }[view.skill];
    const edgeMat = lit(stageColor, .3, stageColor);
    edgeMaterial = edgeMat;
    mesh(platform, geo(new THREE.CylinderGeometry(3.45, 3.55, .14, 64)), stageMat, [0, 0, 0], [1, 1, 1]);
    const ring = mesh(platform, geo(new THREE.TorusGeometry(3.3, .025, 5, 80)), edgeMat, [0, .08, 0], [1, 1, 1]); ring.rotation.x = Math.PI / 2;
    const innerRing = mesh(platform, geo(new THREE.TorusGeometry(2.5, .012, 4, 64)), stageMat, [0, .082, 0], [1, 1, 1]); innerRing.rotation.x = Math.PI / 2;
    for (let i = 0; i < 16; i++) {
      const angle = i / 16 * Math.PI * 2;
      const marker = mesh(platform, cube, edgeMat, [Math.sin(angle) * 3.1, .09, Math.cos(angle) * 3.1], [.06, .015, .16]); marker.rotation.y = angle;
    }
    for (const x of [-1.45, 1.45]) {
      const pad = mesh(platform, geo(new THREE.TorusGeometry(.6, .012, 4, 32)), edgeMat, [x, .087, 0], [1, 1, 1]); pad.rotation.x = Math.PI / 2;
    }
    consolidate(platform);
    buildFighters();
    pose(motion === "recap" ? duration : 0);
    observer = new ResizeObserver(resize); observer.observe(host);
    resize(); emit();
  } catch (error) { dispose(); throw error; }
  return {
    setView(next) {
      if (disposed) return;
      const previous = view; view = next;
      if (next.key !== previous.key) {
        stopFrame(); lastCount = next.usable;
        try {
          buildFighters();
          begin(next.replayFinal === false ? "exchange" : next.mode === "recap" ? "recap" : "intro");
          resize(); emit();
        } catch { fatal("This 3D view could not open. Your evidence remains available in 2D."); }
        return;
      }
      if (next.replayStep !== previous.replayStep) {
        begin(next.replayFinal ? "recap" : "exchange");
      } else if (next.mode === "battle" && next.usable !== null && lastCount !== null && next.usable > lastCount && !next.paused && active) {
        // Coalesce new evidence while an exchange runs; never build an animation backlog.
        if (!frame) begin("exchange");
      }
      lastCount = next.usable;
    },
    setActive(value) { if (disposed || value === active) return; active = value; if (!active) stopFrame(); else if (elapsed < duration) frame = requestAnimationFrame(tick); },
    setQuality(quality) { if (disposed) return; const tier = governor.tier; governor.setPreference(quality); if (tier !== governor.tier) { resize(); emit(); } },
    replay() { if (!disposed) begin(view.mode === "recap" ? "recap" : "pose"); },
    finish() { if (!disposed) { elapsed = duration; stopFrame(); pose(duration); draw(); emit(); } },
    dispose,
  };
}

import type { Fighter } from "./model";

// Shared front-facing details: SVG and 3D use these same normalized line segments.
export type Segment = readonly [number, number, number, number];
export const VISORS: readonly (readonly Segment[])[] = [
  [[-.85, 0, .85, 0]],
  [[-.85, .22, -.15, -.12], [.15, -.12, .85, .22]],
  [[-.75, .25, -.75, -.25], [0, .25, 0, -.25], [.75, .25, .75, -.25]],
  [[-.85, 0, -.4, .3], [-.4, .3, .4, .3], [.4, .3, .85, 0]],
];
export const EMBLEMS: readonly (readonly Segment[])[] = [
  [[-.8, .65, 0, 1], [0, 1, .8, .65], [-.8, -.45, 0, -.85], [0, -.85, .8, -.45]],
  [[-1, .75, -1, -.65], [1, .75, 1, -.65]],
  [[-.85, .75, -.4, .75], [.4, .75, .85, .75], [-.85, -.7, -.4, -.7], [.4, -.7, .85, -.7]],
  [[-.95, 0, -.7, .4], [-.7, .4, -.45, 0], [.45, 0, .7, -.4], [.7, -.4, .95, 0]],
];
export function familyMark(family: Fighter["family"]): readonly Segment[] {
  if (family === "Linear") return [[-.3, -.45, -.3, .45], [0, -.45, 0, .45], [.3, -.45, .3, .45]];
  if (family === "XGBoost") return [[0, -.5, 0, .1], [0, .1, -.4, .45], [0, .1, .4, .45], [-.4, .45, -.4, .65], [.4, .45, .4, .65]];
  if (family === "Deterministic") return [[-.4, .4, .4, .4], [.4, .4, .3, -.2], [.3, -.2, 0, -.5], [0, -.5, -.3, -.2], [-.3, -.2, -.4, .4]];
  return [[0, .45, .4, 0], [.4, 0, 0, -.45], [0, -.45, -.4, 0], [-.4, 0, 0, .45]];
}
export const ATTACK_NAMES = ["Straight strike", "Arc strike", "Rising strike", "Double feint"] as const;
export const DEFENCE_NAMES = ["High guard", "Cross guard", "Sidestep"] as const;
export const POSE_NAMES = ["Salute", "Ready stance", "Quiet bow"] as const;

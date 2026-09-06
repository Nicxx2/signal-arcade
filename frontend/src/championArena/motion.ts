import { seedFor } from "./model";
import type { Fighter, Outcome } from "./model";

export const MOTION_VERSION = "arc-motion-v2";
export type Motion = "intro" | "exchange" | "recap" | "pose";
export const ease = (value: number) => { const v = Math.max(0, Math.min(1, value)); return v * v * (3 - 2 * v); };
const pulse = (time: number, start: number, duration: number) => Math.sin(Math.PI * ease((time - start) / duration));
export interface MovePlan { attack: number; defence: number; hand: number; pose: number; celebration: number }
export function movePlan(fighter: Fighter, battle: string, checkpoint: string): MovePlan {
  const seed = seedFor(JSON.stringify([MOTION_VERSION, battle, fighter.id, checkpoint]));
  // Each fighter has a preferred strike and a secondary variation; no random rerolls on opening.
  return { attack: (fighter.details.attack + ((seed >>> 8) % 3 === 0 ? 1 : 0)) % 4, defence: fighter.details.defence, hand: (seed >>> 16) % 2, pose: fighter.details.pose, celebration: fighter.details.celebration };
}
export function isWinner(outcome: Outcome | null, left: boolean): boolean {
  return outcome === "promoted" ? !left : outcome === "defended" || outcome === "first_champion" ? left : false;
}
export interface MotionState {
  motion: Motion; time: number; duration: number; left: boolean; paired: boolean;
  advantage: boolean; outcome: Outcome | null;
}

/** Bounded cosmetic joint offsets. Evidence/outcome are inputs, never outputs of the choreography. */
export function sampleMotion(plan: MovePlan, state: MotionState) {
  const { motion, duration, left, paired, advantage, outcome } = state;
  const time = Math.max(0, Math.min(duration, state.time));
  const direction = left ? 1 : -1;
  const transient = Math.sin(Math.PI * time / duration);
  const pose = {
    x: 0, yaw: direction * .28, torsoYaw: 0, torsoLean: 0,
    torsoY: 1.6 + Math.sin(time * 3 + (left ? 0 : 1)) * .018 * transient,
    headPitch: 0, headYaw: Math.sin(time * 1.5) * .09 * transient,
    armX: [-.1, -.1], armZ: [-.12, .12], forearmX: [-.22, -.22],
    crown: false,
  };
  const signaturePose = (amount: number) => {
    if (plan.pose === 0) { pose.armX[1]! -= amount * .9; pose.forearmX[1]! -= amount * 1.2; }
    else if (plan.pose === 1) {
      pose.armX[0]! -= amount * .45; pose.armX[1]! -= amount * .45;
      pose.forearmX[0]! -= amount * .9; pose.forearmX[1]! -= amount * .9;
      pose.torsoYaw = direction * amount * .2;
    } else { pose.armX[1]! -= amount * .55; pose.forearmX[1]! -= amount * 1.35; pose.headPitch = amount * .25; }
  };
  if (motion === "intro") {
    const arrive = 1 - ease(time / 1.4);
    pose.x = -direction * arrive * .4; pose.yaw += direction * arrive * .35;
    signaturePose(pulse(time, .9, 2));
  } else if (motion === "pose") signaturePose(pulse(time, 0, duration));
  else {
    const stage = motion === "recap" ? Math.min(time, 2.8) : time * 2.8 / duration;
    const start = left ? .2 : .9;
    const attack = paired ? pulse(stage, start, 1.4) : 0;
    const guard = paired ? pulse(stage, left ? .9 : .2, 1.4) : 0;
    const hand = plan.hand, other = 1 - hand;
    const strength = advantage ? 1.15 : 1;
    pose.x = direction * attack * .23;
    pose.torsoYaw = direction * attack * .2;
    if (plan.attack === 0) { // Straight strike.
      pose.armX[hand]! -= attack * 1.2 * strength; pose.forearmX[hand]! -= attack * .25;
    } else if (plan.attack === 1) { // Arcing strike, using the same bounded rig.
      pose.armX[hand]! -= attack * .9 * strength; pose.forearmX[hand]! -= attack * .8;
      pose.armZ[hand]! += (hand === 0 ? -1 : 1) * attack * .55;
      pose.torsoYaw += direction * attack * .2;
    } else if (plan.attack === 2) {
      pose.armX[hand]! -= attack * 1.6 * strength; pose.forearmX[hand]! -= attack * .9;
      pose.torsoLean = direction * attack * .06;
    } else {
      const first = paired ? pulse(stage, start, .75) : 0;
      const second = paired ? pulse(stage, start + .45, .85) : 0;
      pose.armX[hand]! -= first * 1.05 * strength; pose.forearmX[hand]! -= first * .5;
      pose.armX[other]! -= second * 1.1 * strength; pose.forearmX[other]! -= second * .35;
    }
    if (plan.defence === 0) {
      pose.armX[other]! -= guard * .85; pose.forearmX[other]! -= guard * .7;
    } else if (plan.defence === 1) {
      for (const i of [0, 1]) { pose.armX[i]! -= guard * .5; pose.forearmX[i]! -= guard * .9; }
      pose.armZ[0]! += guard * .15; pose.armZ[1]! -= guard * .15;
    } else {
      pose.x -= direction * guard * .16; pose.torsoLean -= direction * guard * .1;
      pose.armX[other]! -= guard * .45; pose.forearmX[other]! -= guard * .8;
    }
    if (motion === "recap") {
      const finish = ease((time - 3) / 1.4);
      const winner = isWinner(outcome, left);
      pose.crown = winner && time >= 3;
      if (winner) {
        pose.yaw = direction * .28 * (1 - finish);
        if (plan.celebration === 0) { pose.armZ[1] = .12 + finish * 1.98; pose.forearmX[1] = -.22 - finish * .7; }
        else if (plan.celebration === 1) {
          pose.armZ[0] = -.12 - finish * 1.75; pose.armZ[1] = .12 + finish * 1.75;
          pose.forearmX[0] = pose.forearmX[1] = -.22 - finish * .6;
        } else { pose.armX[1] = -.1 - finish * .65; pose.forearmX[1] = -.22 - finish * 1.6; pose.headPitch = finish * .12; }
      } else if (outcome && outcome !== "inconclusive" && paired) {
        pose.x -= direction * finish * .35; pose.headPitch = finish * .22;
      }
    }
  }
  return pose;
}

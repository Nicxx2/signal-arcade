import { describe, expect, test } from "vitest";
import { makeFighter, seedFor } from "./model";
import { familyMark } from "./design";
import { isWinner, movePlan, sampleMotion } from "./motion";
import type { Motion, MovePlan } from "./motion";

test("added cosmetics retain the original colours, build, crest and identity", () => {
  const palettes = ["#68e8e1", "#b79aff", "#ffc37d", "#82bcff", "#f49bc5", "#a6e395"];
  for (const id of ["champion", "candidate", "same-name-a", "same-name-b", "🛡️-long-artifact-".repeat(30)]) {
    const fighter = makeFighter(id, "Name", "linear", "entry"), seed = seedFor(`arc-forged-v1:entry:${id}`);
    expect([fighter.color, fighter.build, fighter.crest, fighter.signature]).toEqual([palettes[seed % 6], (seed >>> 8) % 3, (seed >>> 16) % 3, seed.toString(16).padStart(8, "0").toUpperCase()]);
    expect(makeFighter(id, "New name", "linear", "entry", "Active").details).toEqual(fighter.details);
    expect(makeFighter(id, "New name", "xgboost", "entry", "Suspended").details).toEqual(fighter.details);
  }
});

test("sequential artifacts cover all bounded part options without obvious repeated kits", () => {
  const fighters = Array.from({ length: 1000 }, (_, i) => makeFighter(`artifact-${i}`, "Same codename", "linear", "entry"));
  for (const part of ["helmet", "visor", "shoulders", "emblem", "attack"] as const) expect([...new Set(fighters.map(f => f.details[part]))].sort()).toEqual([0, 1, 2, 3]);
  for (const part of ["trim", "defence", "pose", "celebration"] as const) expect([...new Set(fighters.map(f => f.details[part]))].sort()).toEqual([0, 1, 2]);
  const looks = new Set(fighters.map(f => JSON.stringify([f.color, f.build, f.crest, f.details.helmet, f.details.visor, f.details.shoulders, f.details.emblem, f.details.trim])));
  expect(looks.size).toBeGreaterThan(950); // A fixture diversity check, not a global uniqueness guarantee.
});

test("family cues are distinct and unknown metadata gets a neutral mark", () => {
  expect(new Set(["Linear", "XGBoost", "Deterministic", "Family unknown"].map(f => JSON.stringify(familyMark(f)))).size).toBe(4);
  expect(familyMark("future-family")).toEqual(familyMark("Family unknown"));
});

test("the added detail recipe has a frozen representative mapping", () => {
  expect(makeFighter("champion", "Name", "linear", "entry").details).toMatchInlineSnapshot(`
    {
      "attack": 1,
      "celebration": 2,
      "defence": 2,
      "emblem": 3,
      "helmet": 3,
      "pose": 1,
      "shoulders": 3,
      "trim": 2,
      "visor": 0,
    }
  `);
});

test("strike and defence styles actually produce different bounded motion", () => {
  const base = { attack: 0, defence: 0, hand: 0, pose: 0, celebration: 0 };
  const state = { motion: "exchange" as const, time: .6, duration: 1.6, left: true, paired: true, advantage: false, outcome: null };
  const strikes = [0, 1, 2, 3].map(attack => sampleMotion({ ...base, attack }, state));
  expect(new Set(strikes.map(p => JSON.stringify([p.armX, p.armZ, p.forearmX]))).size).toBe(4);
  const guards = [0, 1, 2].map(defence => sampleMotion({ ...base, defence }, { ...state, time: 1 }));
  expect(new Set(guards.map(p => JSON.stringify([p.x, p.armX, p.forearmX]))).size).toBe(3);
});

test("a fighter keeps its preferred repertoire and replays exactly after a rename or reopen", () => {
  const fighter = makeFighter("champion", "Old", "linear", "entry");
  const renamed = makeFighter("champion", "New", "linear", "entry", "Active");
  const plans = Array.from({ length: 32 }, (_, i) => movePlan(fighter, "battle-A", `checkpoint-${i}`));
  plans.forEach((plan, i) => expect(movePlan(renamed, "battle-A", `checkpoint-${i}`)).toEqual(plan));
  expect(new Set(plans.map(p => p.attack)).size).toBe(2);
  expect(new Set(plans.map(p => p.hand)).size).toBe(2);
  expect(plans.map(p => p.attack)).not.toEqual(Array.from({ length: 32 }, (_, i) => movePlan(fighter, "battle-B", `checkpoint-${i}`).attack));
});

describe("bounded motion and truthful results", () => {
  const base: MovePlan = { attack: 0, defence: 0, hand: 0, pose: 0, celebration: 0 };
  test.each([null, "inconclusive"] as const)("%s never celebrates either fighter", outcome => {
    for (const left of [false, true]) for (const celebration of [0, 1, 2]) {
      expect(isWinner(outcome, left)).toBe(false);
      const result = sampleMotion({ ...base, celebration }, { motion: "recap", time: 5.8, duration: 5.8, left, paired: true, advantage: true, outcome });
      expect(result.crown).toBe(false); expect(result.armZ[0]).toBeCloseTo(-.12); expect(result.armZ[1]).toBeCloseTo(.12);
    }
  });
  test.each(["first_champion", "defended", "promoted"] as const)("%s crowns only the saved winner at the final beat", outcome => {
    for (const left of [false, true]) {
      const state = { motion: "recap" as const, duration: 5.8, left, paired: outcome !== "first_champion", advantage: !left, outcome };
      expect(sampleMotion(base, { ...state, time: 2.9 }).crown).toBe(false);
      expect(sampleMotion(base, { ...state, time: 5.8 }).crown).toBe(outcome === "promoted" ? !left : left);
    }
  });
  test("solo introductions and first crowns do not strike an imaginary opponent", () => {
    for (const attack of [0, 1, 2, 3]) for (const defence of [0, 1, 2]) for (const time of [.5, 1, 2, 2.8]) {
      const result = sampleMotion({ ...base, attack, defence }, { motion: "recap", time, duration: 5.8, left: true, paired: false, advantage: false, outcome: "first_champion" });
      expect(result.armX).toEqual([-.1, -.1]); expect(result.forearmX).toEqual([-.22, -.22]); expect(result.x).toBe(0);
    }
  });
  test("all move combinations stay finite, in the stage and within joint limits", () => {
    for (const attack of [0, 1, 2, 3]) for (const defence of [0, 1, 2]) for (const pose of [0, 1, 2]) for (const celebration of [0, 1, 2]) for (const left of [false, true]) {
      for (const motion of ["intro", "pose", "exchange", "recap"] as Motion[]) {
        const duration = motion === "recap" ? 5.8 : motion === "exchange" ? 1.6 : 3.2;
        for (let i = 0; i <= 30; i++) {
          const result = sampleMotion({ attack, defence, pose, celebration, hand: left ? 1 : 0 }, { motion, duration, time: i / 30 * duration, left, paired: true, advantage: true, outcome: "promoted" });
          const numbers = [result.x, result.yaw, result.torsoYaw, result.torsoLean, result.torsoY, result.headPitch, result.headYaw, ...result.armX, ...result.armZ, ...result.forearmX];
          expect(numbers.every(Number.isFinite)).toBe(true);
          expect(Math.abs(result.x)).toBeLessThanOrEqual(.4);
          expect(Math.max(...result.armX.map(Math.abs), ...result.forearmX.map(Math.abs), ...result.armZ.map(Math.abs))).toBeLessThan(Math.PI);
          expect(result.crown && motion !== "recap").toBe(false);
        }
      }
    }
  });
});

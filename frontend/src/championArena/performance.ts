import type { Quality } from "./model";

export type Tier = "low" | "medium" | "high";
export const TIERS: Tier[] = ["low", "medium", "high"];
export const DPR: Record<Tier, number> = { low: 1, medium: 1.25, high: 1.5 };
export const FPS: Record<Tier, number> = { low: 30, medium: 30, high: 60 };
export const AUTO_TIER_KEY = "signal-arcade-champion-auto-tier-v1";
let sessionAutoTier: Tier | null = null;
export function readAutoTier(): Tier {
  if (sessionAutoTier) return sessionAutoTier;
  try {
    const value = localStorage.getItem(AUTO_TIER_KEY);
    if (value === "low" || value === "medium" || value === "high") return value;
  } catch { /* A blocked store still allows safe graphics. */ }
  return "low";
}
function rememberAutoTier(tier: Tier) {
  try { localStorage.setItem(AUTO_TIER_KEY, tier); sessionAutoTier = null; }
  catch { sessionAutoTier = tier; }
}

/** Only active frames count. Hidden/idle wall time cannot upgrade quality. */
export class QualityGovernor {
  tier: Tier;
  private work: number[] = [];
  private intervals: number[] = [];
  private activeMs = 0;
  private stableMs = 0;
  private badWindows = 0;
  private cooldownMs = 0;
  constructor(private preference: Quality) { this.tier = this.initialTier(preference); }
  private initialTier(preference: Quality): Tier { return preference === "auto" ? readAutoTier() : preference === "high" || preference === "medium" ? preference : "low"; }
  setPreference(preference: Quality) {
    if (this.preference === preference) return;
    this.preference = preference;
    this.tier = this.initialTier(preference);
    this.reset();
  }
  private reset() { this.work = []; this.intervals = []; this.activeMs = 0; this.stableMs = 0; this.badWindows = 0; this.cooldownMs = 0; }
  sample(workMs: number, intervalMs: number): Tier | "fallback" | null {
    if (!Number.isFinite(workMs) || !Number.isFinite(intervalMs) || intervalMs <= 0) return null;
    this.work.push(workMs); this.intervals.push(intervalMs);
    this.activeMs += Math.min(250, intervalMs);
    this.cooldownMs = Math.max(0, this.cooldownMs - intervalMs);
    if (this.activeMs < 2_000) return null;
    const work = this.work.sort((a, b) => a - b);
    const intervals = this.intervals.sort((a, b) => a - b);
    const p95 = work[Math.floor((work.length - 1) * .95)] ?? 0;
    const medianFrame = intervals[Math.floor(intervals.length / 2)] ?? 0;
    const bad = p95 > (this.tier === "high" ? 18 : 35) || medianFrame > (this.tier === "high" ? 30 : 50);
    const windowMs = this.activeMs;
    this.work = []; this.intervals = []; this.activeMs = 0;
    this.badWindows = bad ? this.badWindows + 1 : 0;
    this.stableMs = !bad && p95 < 8 && medianFrame < 40 ? this.stableMs + windowMs : 0;
    if (this.badWindows >= 3 && this.cooldownMs === 0) {
      if (this.tier === "low") return "fallback";
      this.tier = this.tier === "high" ? "medium" : "low";
      if (this.preference === "auto") rememberAutoTier(this.tier);
      this.badWindows = 0; this.stableMs = 0; this.cooldownMs = 10_000;
      return this.tier;
    }
    if (this.preference === "auto" && this.stableMs >= 30_000 && this.cooldownMs === 0 && this.tier !== "high") {
      this.tier = this.tier === "low" ? "medium" : "high";
      rememberAutoTier(this.tier);
      this.stableMs = 0; this.cooldownMs = 10_000;
      return this.tier;
    }
    return null;
  }
}

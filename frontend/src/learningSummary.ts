import type { LearningStatus } from "./types";

export function challengerOverviewSummary(learning: LearningStatus): string {
  if (!learning.collecting_from_current_source) return "Saved proof · source separate";
  if (learning.mode === "off") return "Learning & support paused";

  const champions = new Set((learning.skills ?? []).filter(skill => skill.champion).map(skill => skill.skill)).size;
  const saved = `${champions} Champion${champions === 1 ? "" : "s"} saved`;
  if (learning.mode === "active") {
    const active = new Set(Object.entries(learning.active_skill_versions ?? {}).filter(([, version]) => version).map(([skill]) => skill));
    if (learning.active_model) active.add("entry");
    if (active.size) return `${active.size} skill${active.size === 1 ? "" : "s"} supporting Baseline · ${saved}`;
    return "Support status updating";
  }
  if (champions) return `${saved} · ${learning.auto_participation ? "waiting for support proof" : "support off"}`;
  if (learning.activation_available) return learning.auto_participation ? "Entry activation proof ready" : "Entry ready · support off";
  return learning.auto_participation ? "Collecting skill proof · automatic support allowed" : "Collecting skill proof · support off";
}

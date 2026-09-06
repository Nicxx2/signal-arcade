import type { ChallengerChampionEvent, ChallengerSkillStatus, Snapshot } from "../types";

export type Skill = ChallengerSkillStatus["skill"];
export type Outcome = ChallengerChampionEvent["kind"];
export type Quality = "auto" | "high" | "medium" | "low" | "off";
export const SKILLS: Record<Skill, string> = { entry: "Entry", manipulation: "Manipulation", sizing: "Sizing", exit: "Exit" };
export const GRAPHICS_KEY = "signal-arcade-champion-graphics-v1";
export const APPEARANCE_VERSION = "arc-forged-v1";
export const DETAILS_VERSION = "arc-details-v1";
export interface FighterDetails {
  helmet: number; visor: number; shoulders: number; emblem: number; trim: number;
  attack: number; defence: number; pose: number; celebration: number;
}
export const OUTCOMES: Record<Outcome, [string, string]> = {
  first_champion: ["A Champion is born", "Independent skill proof established the first Champion. Influence is separately gated."],
  promoted: ["A new reign begins", "The contender proved the required advantage on shared forward outcomes."],
  defended: ["The crown stays", "The contender did not establish the safe advantage required for replacement."],
  inconclusive: ["The evidence stays open", "This comparison ended without a trustworthy replacement result."],
};
export interface Fighter {
  id: string; name: string; family: string; skill: Skill; seed: number; color: string;
  trim: string; build: number; crest: number; signature: string; influence: string;
  details: FighterDetails;
}
export interface ArenaView {
  key: string; context: string; skill: Skill;
  mode: "battle" | "training" | "champion" | "recap" | "interrupted";
  left: Fighter | null; right: Fighter | null;
  leftIsChampion: boolean;
  title: string; detail: string; outcome: Outcome | null; event: ChallengerChampionEvent | null;
  usable: number | null; observed: number | null; coverage: number | null;
  mean: number | null; lower: number | null; upper: number | null;
  minimum: number; minimumCoverage: number; momentum: "left" | "right" | "neutral";
  generation: number | null; paused: boolean; gates: ChallengerSkillStatus["gates"];
  replayStep?: number; replayFinal?: boolean; replayAt?: string;
  evidenceAt?: string; superseded?: boolean;
}
export interface Selection { context: string; initial: ArenaView }

// Frozen cosmetic recipe. Never use this hash for authority, uniqueness, or model identity.
export function seedFor(value: string): number {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) hash = Math.imul(hash ^ value.charCodeAt(i), 16777619);
  return hash >>> 0;
}
const PALETTES = [["#68e8e1", "#bbfff3"], ["#b79aff", "#eee2ff"], ["#ffc37d", "#ffedce"], ["#82bcff", "#d7ebff"], ["#f49bc5", "#ffe3f0"], ["#a6e395", "#e5ffdc"]] as const;
// Independent, frozen detail lanes leave the original colours, silhouette and signature intact.
// The final mixing avoids correlated low bits when many sequential artifact IDs are generated.
function fighterDetails(id: string, skill: Skill): FighterDetails {
  const pick = (part: string, count: number) => {
    let h = seedFor(`${DETAILS_VERSION}:${skill}:${id}:${part}`);
    h = Math.imul(h ^ (h >>> 16), 0x85ebca6b);
    h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
    return ((h ^ (h >>> 16)) >>> 0) % count;
  };
  return { helmet: pick("helmet", 4), visor: pick("visor", 4), shoulders: pick("shoulders", 4), emblem: pick("emblem", 4), trim: pick("trim", 3), attack: pick("attack", 4), defence: pick("defence", 3), pose: pick("pose", 3), celebration: pick("celebration", 3) };
}
export function makeFighter(id: string, name: string | null | undefined, family: string | null | undefined, skill: Skill, influence = "Shadow"): Fighter {
  const seed = seedFor(`${APPEARANCE_VERSION}:${skill}:${id}`);
  const palette = PALETTES[seed % PALETTES.length]!;
  return { id, name: name?.trim() || "Unnamed contender", family: family === "xgboost" ? "XGBoost" : family === "linear" ? "Linear" : family === "deterministic" ? "Deterministic" : "Family unknown", skill, seed, color: palette[0], trim: palette[1], build: (seed >>> 8) % 3, crest: (seed >>> 16) % 3, signature: seed.toString(16).padStart(8, "0").toUpperCase(), influence, details: fighterDetails(id, skill) };
}
// Full IDs are the final collision fallback; a cosmetic hash is never an identity key.
export function displaySignatures(left: Fighter | null, right: Fighter | null): [string, string] {
  if (left && right && left.id !== right.id && left.signature === right.signature) return [left.id, right.id];
  return [left?.signature ?? "", right?.signature ?? ""];
}
export function contextFor(snapshot: Snapshot): string {
  return `${snapshot.demo_mode ? "demo" : "mainnet"}:${snapshot.risk_mode}:${snapshot.learning.champion_journey_cohort_key ?? snapshot.season_profile?.learning_fingerprint ?? snapshot.learning.latest_model?.configuration_fingerprint ?? "legacy"}`;
}
export function finite(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function count(value: unknown): number | null { const n = finite(value); return n !== null && Number.isInteger(n) && n >= 0 ? n : null; }
function fraction(value: unknown): number | null { const n = finite(value); return n !== null && n >= 0 && n <= 1 ? n : null; }
export function pairKey(context: string, skill: Skill, champion: string | null, candidate: string | null): string { return JSON.stringify([context, skill, champion, candidate]); }
export function percentage(value: number | null, signed = false): string { return value === null ? "Unknown" : `${signed && value > 0 ? "+" : ""}${(value * 100).toFixed(1)}${signed ? " pp" : "%"}`; }
export function recordedDate(value: string | undefined): string { const timestamp = Date.parse(value ?? ""); return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : "Recorded date unavailable"; }

export function viewForSkill(snapshot: Snapshot, skill: Skill): ArenaView | null {
  const status = snapshot.learning.skills?.find((item) => item.skill === skill);
  if (!status || (!status.champion && !status.latest_candidate && !status.testing_candidate)) return null;
  const context = contextFor(snapshot);
  const influence = (id: string) => status.active_version === id ? "Active" : status.state === "suspended" && status.champion?.version === id ? "Suspended" : "Shadow";
  const artifact = (item: ChallengerSkillStatus["latest_candidate"]) => item?.version ? makeFighter(item.version, item.codename, item.model_family, skill, influence(item.version)) : null;
  const testing = status.testing_version ? [status.testing_candidate, status.latest_candidate].find((item) => item?.version === status.testing_version) ?? null : null;
  const champion = artifact(status.champion);
  const candidate = artifact(testing ?? status.latest_candidate);
  const hasPair = Boolean(status.testing_version && champion && testing && champion.id !== testing.version);
  const mode = hasPair ? "battle" : status.testing_version ? "interrupted" : champion ? "champion" : "training";
  const t = status.tournament;
  const matched = hasPair && t.candidate_version === testing?.version && t.champion_version === champion?.id;
  const usable = matched ? count(t.common_usable_count) : mode === "battle" ? count(status.common_forward_count) : null;
  const observed = matched ? count(t.common_observed_count) : null;
  const coverage = matched ? fraction(t.availability_fraction) : null;
  const lower = matched ? finite(t.uplift_lower_bound) : null;
  const upper = matched ? finite(t.uplift_upper_bound) : null;
  const mean = matched ? finite(t.mean_uplift) : null;
  const minimum = count(snapshot.learning.challenger_common_forward_minimum) ?? 30;
  const minimumCoverage = fraction(snapshot.learning.challenger_minimum_availability) ?? 0.7;
  const supported = usable !== null && observed !== null && usable <= observed && usable >= minimum && coverage !== null && coverage >= minimumCoverage;
  const paused = snapshot.learning.mode === "off" || !snapshot.learning.collecting_from_current_source || status.state === "suspended";
  return {
    key: pairKey(context, skill, champion?.id ?? null, status.testing_version ?? (champion ? null : candidate?.id ?? null)), context, skill, mode,
    left: champion ?? candidate, right: hasPair ? artifact(testing) : null, leftIsChampion: Boolean(champion),
    title: mode === "battle" ? "Proof in motion" : mode === "champion" ? "Meet your Champion" : mode === "training" ? "The next contender" : "Battle unavailable",
    detail: paused ? "Learning is paused, separate from this source, or suspended. Saved proof remains visible." : mode === "battle" ? "New shared evidence shapes the comparison. Every promotion guard still has to pass." : mode === "champion" ? "No battle is underway. A candidate must qualify and enter a comparison before an opponent appears. Influence remains separately gated." : mode === "training" ? "Independent proof comes first. Training here is a visual introduction, not a new model fit." : "A testing artifact is unavailable. No result can be inferred.",
    outcome: null, event: null, usable, observed, coverage,
    mean, lower, upper, minimum, minimumCoverage,
    momentum: !paused && supported && lower !== null && upper !== null && mean !== null && lower <= mean && mean <= upper ? lower > 0 ? "right" : upper < 0 ? "left" : "neutral" : "neutral",
    generation: count(status.champion_generation), paused, gates: status.gate_artifact_version && status.gate_artifact_version !== (testing ?? status.latest_candidate)?.version ? [] : status.gates ?? [],
    evidenceAt: snapshot.snapshot_generated_at,
  };
}

export function viewForEvent(snapshot: Snapshot, event: ChallengerChampionEvent): ArenaView {
  const context = contextFor(snapshot);
  const current = snapshot.learning.skills?.find((item) => item.skill === event.skill);
  const influence = (id: string) => current?.active_version === id ? "Active now" : current?.state === "suspended" && current.champion?.version === id ? "Suspended now" : "Historical artifact";
  const first = event.kind === "first_champion";
  const leftId = first ? event.champion_version : event.previous_champion_version;
  const left = leftId ? makeFighter(leftId, first ? event.champion_codename : event.previous_champion_codename, first ? event.champion_model_family : event.previous_champion_model_family, event.skill, influence(leftId)) : null;
  const right = !first && event.candidate_version ? makeFighter(event.candidate_version, event.candidate_codename, event.candidate_model_family, event.skill, influence(event.candidate_version)) : null;
  const copy = OUTCOMES[event.kind] ?? ["Recorded result", "Result information is unavailable."];
  return { key: event.event_id, context, skill: event.skill, mode: "recap", left, right, leftIsChampion: true, title: copy[0], detail: event.resolution || copy[1], outcome: event.kind, event: { ...event }, usable: count(event.common_usable_count), observed: count(event.common_observed_count), coverage: fraction(event.availability_fraction), mean: finite(event.mean_uplift), lower: finite(event.uplift_lower_bound), upper: null, minimum: 0, minimumCoverage: 0, momentum: "neutral", generation: null, paused: false, gates: [] };
}

export function matchingEvent(view: ArenaView, events: ChallengerChampionEvent[]): ChallengerChampionEvent | undefined {
  if (view.mode !== "battle" || !view.left || !view.right) return undefined;
  return events.find((event) => event.skill === view.skill && event.previous_champion_version === view.left!.id && event.candidate_version === view.right!.id && event.kind !== "first_champion");
}

export function resolveSelection(snapshot: Snapshot, selection: Selection, extraEvents: ChallengerChampionEvent[] = []): ArenaView | null {
  if (selection.context !== contextFor(snapshot)) return null;
  const initial = selection.initial;
  if (initial.mode === "recap") return initial.event ? viewForEvent(snapshot, initial.event) : initial;
  const event = matchingEvent(initial, [...(snapshot.learning.champion_journey ?? []), ...extraEvents]);
  if (event) return viewForEvent(snapshot, event);
  const current = viewForSkill(snapshot, initial.skill);
  if (current?.key === initial.key) return current;
  // Keep an opened profile tied to its artifact. A new generation is not a lost battle.
  if (initial.mode === "training" || initial.mode === "champion") {
    if (current?.leftIsChampion && current.left?.id === initial.left?.id) {
      if (current.mode === "champion") return current;
      return { ...current, key: initial.key, mode: "champion", right: null, title: "Meet your Champion",
        detail: `This Champion is now in a comparison. Select ${SKILLS[initial.skill]} above to watch it.` };
    }
    return { ...initial, superseded: true, paused: true, momentum: "neutral",
      title: initial.mode === "training" ? current ? "Newer contender available" : "Saved contender profile" : "Saved Champion profile",
      detail: `You’re viewing the selected model version and its last displayed proof. ${current ? `Select ${SKILLS[initial.skill]} above to see the current profile.` : "A current profile is not available."}` };
  }
  return { ...initial, mode: "interrupted", paused: true, momentum: "neutral", title: "The comparison changed", detail: "This pair is no longer testing. Its result may be in Champion Journey; no outcome is inferred from its disappearance." };
}

export function freshness(snapshot: Snapshot, elapsedSeconds: number): number | null {
  const generated = Date.parse(snapshot.snapshot_generated_at ?? "");
  const server = Date.parse(snapshot.server_time);
  const reported = finite(snapshot.snapshot_age_seconds);
  if (!Number.isFinite(generated) || !Number.isFinite(server) || generated > server + 1_000 || (reported !== null && reported < 0)) return null;
  return Math.max(reported ?? 0, (server - generated) / 1000, 0) + Math.max(0, elapsedSeconds);
}

let sessionQuality: Quality | null = null;
export function writeQuality(value: Quality) {
  try { localStorage.setItem(GRAPHICS_KEY, value); sessionQuality = null; }
  catch { sessionQuality = value; }
}
export function readQuality(): Quality {
  if (sessionQuality) return sessionQuality;
  try { const value = localStorage.getItem(GRAPHICS_KEY); if (["auto", "high", "medium", "low", "off"].includes(value ?? "")) return value as Quality; } catch { /* Session-only preference remains usable. */ }
  return "auto";
}

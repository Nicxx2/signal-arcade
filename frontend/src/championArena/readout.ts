import type { ArenaView } from "./model";
import { percentage } from "./model";

export const SCALE = .05;
export const position = (value: number) => 50 + Math.max(-1, Math.min(1, value / SCALE)) * 50;
export const numeric = (value: number | null): value is number => value !== null && Number.isFinite(value);

// This is a measured value difference on a fixed scale, never a probability or a promotion score.
export function edgeText(value: number | null): string {
  if (!numeric(value)) return "Unknown";
  if (value === 0) return "0.0 pp";
  if (Math.abs(value) < .0001) return value > 0 ? "+<0.01 pp" : "−<0.01 pp";
  return `${value > 0 ? "+" : "−"}${(Math.abs(value) * 100).toFixed(Math.abs(value) < .001 ? 2 : 1)} pp`;
}

export function nextCheckText(gate: ArenaView["gates"][number]): string {
  if (gate.unit === "boolean") return "All qualification checks for this skill must pass together.";
  const valueCheck = /value|uplift/i.test(gate.label);
  const format = (value: unknown) => typeof value !== "number" || !Number.isFinite(value) ? "Unknown" : gate.unit === "fraction" ? valueCheck ? edgeText(value) : percentage(value) : Number.isInteger(value) ? String(value) : value.toFixed(2);
  const explanation = /coverage/i.test(gate.label) ? "Enough observed outcomes must have a usable result."
    : valueCheck ? "The evidence must support an improvement after costs."
      : /winner veto/i.test(gate.label) ? "Avoid blocking too many profitable opportunities."
        : gate.unit === "count" ? "Enough usable examples are needed for this check."
          : "This check still needs to pass.";
  return `${explanation} Current: ${format(gate.current)}; required: ${gate.comparison} ${format(gate.target)}.`;
}

export function battleReadout(view: ArenaView, stale: boolean) {
  const checkpoint = view.replayFinal === false;
  const historical = view.mode === "recap" && !checkpoint;
  const champion = view.left?.name ?? "The saved Champion";
  const contender = view.right?.name ?? "The contender";
  const counts = numeric(view.usable) && numeric(view.observed) && Number.isInteger(view.usable) && Number.isInteger(view.observed) && view.usable > 0 && view.usable <= view.observed;
  const coverage = numeric(view.coverage) && view.coverage >= 0 && view.coverage <= 1;
  const enough = counts && coverage && view.usable! >= view.minimum && view.minimum > 0 && view.coverage! >= view.minimumCoverage && view.minimumCoverage > 0;
  const bounds = numeric(view.mean) && numeric(view.lower) && numeric(view.upper) && view.lower <= view.mean && view.mean <= view.upper;
  // Delayed delivery does not invalidate the last measured comparison. Label its age,
  // while the renderer still pauses exchanges and missing/mismatched proof stays unknown.
  const live = checkpoint || (!historical && !view.paused && view.mode === "battle");
  const delayed = !historical && !checkpoint && stale && live;
  // A descriptive average can be shown before qualification. Only sufficient, bounded proof
  // may be called a supported edge; the server alone decides replacement.
  const plot = counts && coverage && numeric(view.mean) && (historical || (live && bounds));
  const band = plot && bounds;
  const preliminary = !historical && plot && (!enough || !bounds || view.lower! <= 0 && view.upper! >= 0);
  const countReady = (historical || live && numeric(view.minimum) && view.minimum > 0) && numeric(view.usable) && numeric(view.observed) && Number.isSafeInteger(view.usable) && Number.isSafeInteger(view.observed) && view.usable >= 0 && view.usable <= view.observed;
  const evidenceText = (delayed ? "Last update · " : "") + (countReady
    ? historical ? `${view.usable} usable · ${percentage(view.coverage)} coverage`
      : `${view.usable} usable · ${preliminary ? "preliminary" : "comparison open"}`
    : historical ? "Recorded evidence unavailable" : "Evidence not available yet");
  const shortTitle = !plot ? historical ? "Average unavailable" : !live ? "Comparison paused" : "Average not available yet"
    : view.mean === 0 ? historical ? "Level result" : delayed ? "Level at last update" : "Level so far"
      : historical ? `Average edge ${edgeText(view.mean)}`
        : `${view.mean! > 0 ? "Contender" : "Champion"} ahead ${delayed ? "at last update" : "on average"}`;
  let title: string, detail: string;
  if (historical) {
    if (view.outcome === "promoted") {
      title = "New Champion crowned";
      detail = `${contender} proved the required safe advantage and replaced ${champion}.`;
    } else if (view.outcome === "defended") {
      title = plot && view.mean === 0 ? "Level result · Champion retained" : "Champion defended the crown";
      detail = view.mean === 0 && view.lower === 0
        ? `No measured advantage for ${contender} on these shared outcomes. ${champion} keeps the crown.`
        : numeric(view.mean) && view.mean > 0
          ? `${contender} had a higher average, but did not prove the safe advantage required for replacement. ${champion} keeps the crown.`
          : `${contender} did not prove the advantage required for replacement. ${champion} keeps the crown.`;
    } else {
      title = "No replacement established";
      detail = `The evidence did not establish a safe replacement. ${champion} remains the saved Champion.`;
    }
  } else if (view.mode === "interrupted") {
    title = "Waiting for this pair’s result";
    detail = "This pair is no longer testing. A saved result is needed before showing a winner.";
  } else if (!checkpoint && view.paused) {
    title = "Comparison paused";
    detail = "Learning must be running and collecting from this source for the comparison to resume. Champion support is separately gated.";
  } else if (!plot) {
    title = "Building the comparison";
    detail = "Usable shared outcomes and a valid estimate are needed to show the average difference. Missing values stay unknown.";
  } else if (view.mean === 0) {
    title = "Level so far";
    detail = "Both fighters have the same measured average on these shared outcomes. More evidence can still change the comparison; no replacement has been recorded.";
  } else if (enough && view.lower! > 0) {
    title = `${contender} has the edge`;
    detail = `${checkpoint ? "The evidence at this checkpoint favored" : "The evidence currently favors"} the contender. Every replacement safety check must still pass.`;
  } else if (enough && view.upper! < 0) {
    title = `${champion} has the edge`;
    detail = "The contender is behind on the shared evidence. The comparison is still open.";
  } else {
    title = `${view.mean! > 0 ? contender : champion} ahead on average`;
    detail = !enough
      ? "Preliminary evidence: sample size or coverage is below the required level. This measured lead can reverse and does not qualify a winner."
      : "Too close to call a safe replacement: the uncertainty range reaches the level point. The higher average is a preliminary lead.";
  }
  if (delayed && plot) {
    title = view.mean === 0 ? "Level at the last update" : `${view.mean! > 0 ? contender : champion} ahead at the last update`;
    detail = view.mean === 0 ? "Both fighters had the same measured average on the last received evidence. New evidence can change the comparison."
      : !preliminary ? "The last measured evidence supported this lead. Every replacement safety check must still pass."
        : detail;
  }
  const exactLevel = plot && view.mean === 0;
  return { title, detail, shortTitle, evidenceText, countReady, plot, band, enough, preliminary, exactLevel, delayed };
}

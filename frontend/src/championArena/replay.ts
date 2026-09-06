import type { BattleReplayTimeline, ChallengerChampionEvent } from "../types";
import type { ArenaView } from "./model";
import { SCALE } from "./readout";

const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const number = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const instant = (value: unknown) => {
  if (typeof value !== "string" || value.length > 40 || !/(?:Z|[+-]\d\d:\d\d)$/.test(value)) return NaN;
  // Python records microseconds. Two real checkpoints can share a JavaScript millisecond.
  const microseconds = Date.parse(value) * 1000 + Number((value.match(/\.\d{3}(\d{1,3})(?:Z|[+-]\d\d:\d\d)$/)?.[1] ?? "").padEnd(3, "0"));
  return Number.isSafeInteger(microseconds) ? microseconds : NaN;
};

/** Treat the optional recording as untrusted; the immutable result remains authoritative. */
export function validateReplay(response: unknown, event: ChallengerChampionEvent, cohort: string): BattleReplayTimeline | null {
  if (!object(response) || response.event_id !== event.event_id || response.cohort_key !== cohort || event.kind === "first_champion") return null;
  const replay = response.timeline;
  if (!object(replay) || replay.version !== "battle-checkpoints-v1" || replay.cohort_key !== cohort || replay.skill !== event.skill || replay.candidate_version !== event.candidate_version || replay.champion_version !== event.previous_champion_version || replay.candidate_version === replay.champion_version) return null;
  if (!count(replay.minimum_samples) || replay.minimum_samples < 1 || replay.minimum_samples > 10000 || !number(replay.minimum_coverage) || replay.minimum_coverage <= 0 || replay.minimum_coverage > 1 || typeof replay.partial !== "boolean" || typeof replay.sampled !== "boolean") return null;
  if (!Array.isArray(replay.points) || replay.points.length < 2 || replay.points.length > 32) return null;
  let time = -Infinity, sequence = -1;
  for (const point of replay.points) {
    if (!object(point) || !count(point.sequence) || point.sequence <= sequence || !Number.isFinite(instant(point.at)) || instant(point.at) <= time) return null;
    time = instant(point.at); sequence = point.sequence;
    if (!count(point.usable) || !count(point.observed) || point.usable > point.observed || !number(point.coverage) || Math.abs(point.coverage - (point.observed ? point.usable / point.observed : 0)) > 1e-9) return null;
    if (![point.mean, point.lower, point.upper].every(value => value === null || number(value))) return null;
    if (number(point.mean) && number(point.lower) && number(point.upper) && !(point.lower <= point.mean && point.mean <= point.upper)) return null;
  }
  const last = replay.points.at(-1)!;
  if (!Number.isFinite(instant(event.occurred_at)) || time > instant(event.occurred_at)) return null;
  if (last.observed !== event.common_observed_count || last.usable !== event.common_usable_count || last.coverage !== event.availability_fraction || last.mean !== event.mean_uplift || last.lower !== event.uplift_lower_bound) return null;
  return replay as unknown as BattleReplayTimeline;
}

export function replayFrame(base: ArenaView, timeline: BattleReplayTimeline, index: number): ArenaView {
  const step = Math.max(0, Math.min(timeline.points.length - 1, Math.trunc(Number.isFinite(index) ? index : 0)));
  const point = timeline.points[step]!;
  const final = step === timeline.points.length - 1;
  const enough = point.usable >= timeline.minimum_samples && point.coverage >= timeline.minimum_coverage;
  const valid = point.mean !== null && point.lower !== null && point.upper !== null && point.lower <= point.mean && point.mean <= point.upper;
  return { ...base, replayStep: step, replayFinal: final, replayAt: point.at,
    title: final ? base.title : "The comparison unfolds", detail: final ? base.detail : "Step through the evidence recorded while these two fighters were compared.",
    outcome: final ? base.outcome : null, usable: point.usable, observed: point.observed, coverage: point.coverage,
    mean: point.mean, lower: point.lower, upper: point.upper, minimum: timeline.minimum_samples, minimumCoverage: timeline.minimum_coverage,
    momentum: enough && valid ? point.lower! > 0 ? "right" : point.upper! < 0 ? "left" : "neutral" : "neutral", paused: false };
}

/** At most 32 saved values. Unknown points break the trail; future points stay hidden. */
export function replayTrail(timeline: BattleReplayTimeline, index: number) {
  const shown = timeline.points.slice(0, Math.max(0, Math.min(timeline.points.length - 1, index)) + 1);
  const dots = shown.map((point, i) => {
    const measured = point.usable > 0 && point.mean !== null && point.lower !== null && point.upper !== null && point.lower <= point.mean && point.mean <= point.upper;
    return measured ? { index: i, mean: point.mean!, x: 10 + 280 * i / Math.max(1, timeline.points.length - 1), y: 44 - 32 * Math.max(-1, Math.min(1, point.mean! / SCALE)) } : null;
  });
  const values = dots.filter(dot => dot !== null);
  const hasGap = dots.some(dot => dot === null);
  const level = values.length > 0 && values.every(dot => dot.mean === 0);
  const bothLed = values.some(dot => dot.mean > 0) && values.some(dot => dot.mean < 0);
  const summary = !values.length ? "No measured average in the shown checkpoints yet."
    : level ? "Level in every measured checkpoint shown."
      : bothLed ? "Both sides led on average in the checkpoints shown."
        : `${values.some(dot => dot.mean > 0) ? "The contender" : "The Champion"} had the higher average in the measured checkpoints shown.`;
  return { dots, summary, hasGap };
}

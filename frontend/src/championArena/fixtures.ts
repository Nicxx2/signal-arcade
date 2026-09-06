import type { BattleReplayResponse, ChallengerChampionEvent, ChallengerSkillStatus, Snapshot } from "../types";

export function artifact(version: string, name = "Steady Sentinel"): NonNullable<ChallengerSkillStatus["latest_candidate"]> {
  return { version, codename: name, created_at: "2026-09-04T12:00:00Z", model_family: "linear", skill: "entry", outcomes_seen: 180, sample_count: 180, training_count: 120, validation_count: 60, embargoed_count: 0, qualified: true, metrics: {}, parameters: {} };
}
export function skillFixture(): ChallengerSkillStatus {
  return { skill: "entry", label: "Entry selection", state: "active", latest_candidate: artifact("future", "Bright Scout"), testing_version: "candidate", testing_candidate: { ...artifact("candidate", "Violet Pathfinder"), model_family: "xgboost" }, champion: artifact("champion"), champion_generation: 2, active_version: "champion", common_forward_count: 35, tournament: { result: "collecting", candidate_version: "candidate", champion_version: "champion", common_usable_count: 35, common_observed_count: 40, availability_fraction: .875, mean_uplift: .024, uplift_lower_bound: -.002, uplift_upper_bound: .05 }, health: { state: "healthy", model_version: "champion", observed_count: 50, usable_count: 45, minimum_samples: 20, availability_fraction: .9, estimated_uplift: .02, uplift_upper_bound: .03 }, gates: [] };
}
export function eventFixture(kind: ChallengerChampionEvent["kind"] = "promoted"): ChallengerChampionEvent {
  return { event_id: `saved-${kind}`, occurred_at: "2026-09-04T12:15:00Z", skill: "entry", kind, candidate_version: "candidate", candidate_codename: "Violet Pathfinder", candidate_model_family: "xgboost", previous_champion_version: kind === "first_champion" ? null : "champion", previous_champion_codename: "Steady Sentinel", previous_champion_model_family: "linear", champion_version: kind === "promoted" || kind === "first_champion" ? "candidate" : "champion", champion_codename: kind === "promoted" || kind === "first_champion" ? "Violet Pathfinder" : "Steady Sentinel", champion_model_family: kind === "promoted" || kind === "first_champion" ? "xgboost" : "linear", common_observed_count: 45, common_usable_count: 41, availability_fraction: .91, mean_uplift: .034, uplift_lower_bound: .012 };
}
/** Minimal, deterministic input boundary; full-app browser checks overlay it on a Demo snapshot. */
export function snapshotFixture(): Snapshot {
  return { risk_mode: "balanced", demo_mode: false, server_time: "2026-09-04T12:10:00Z", snapshot_generated_at: "2026-09-04T12:10:00Z", snapshot_age_seconds: 0, season_profile: null, learning: { mode: "active", collecting_from_current_source: true, champion_journey_cohort_key: "balanced-config-v1", challenger_common_forward_minimum: 30, challenger_minimum_availability: .7, skills: [skillFixture()], champion_journey: [] } } as unknown as Snapshot;
}

export function replayFixture(): { event: ChallengerChampionEvent; response: BattleReplayResponse } {
  const event = { ...eventFixture("defended"), common_observed_count: 60, common_usable_count: 55, availability_fraction: 55 / 60, mean_uplift: -.035, uplift_lower_bound: -.05 };
  return { event, response: { event_id: event.event_id, cohort_key: "balanced-config-v1", timeline: {
    version: "battle-checkpoints-v1", cohort_key: "balanced-config-v1", skill: "entry", candidate_version: "candidate", champion_version: "champion", minimum_samples: 30, minimum_coverage: .7, partial: false, sampled: false,
    points: [
      { sequence: 0, at: "2026-09-04T12:00:00Z", observed: 0, usable: 0, coverage: 0, mean: null, lower: null, upper: null },
      { sequence: 1, at: "2026-09-04T12:05:00Z", observed: 40, usable: 30, coverage: .75, mean: .03, lower: -.01, upper: .07 },
      { sequence: 2, at: "2026-09-04T12:10:00Z", observed: 50, usable: 40, coverage: .8, mean: -.01, lower: -.03, upper: .01 },
      { sequence: 3, at: "2026-09-04T12:15:00Z", observed: 60, usable: 55, coverage: 55 / 60, mean: -.035, lower: -.05, upper: -.02 },
    ],
  } } };
}

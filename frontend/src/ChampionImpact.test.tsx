import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ChampionImpact } from "./ChampionImpact";
import type { ChampionImpactComparison, ChampionImpactReport, ChallengerSkillStatus, LearningStatus } from "./types";

afterEach(cleanup);
const at = "2026-09-13T10:00:00Z";
const comparison: ChampionImpactComparison = {
  subject: "sizing", state: "positive", observed_count: 60, usable_count: 45, pending_count: 3, not_reached_count: 0,
  coverage: 0.75, mean_advantage: 0.05, lower_bound: 0.01, upper_bound: 0.09, reference_mean: -0.1, supported_mean: -0.05,
  from: "2026-09-13T08:00:00Z", to: "2026-09-13T09:00:00Z", reference_horizon_seconds: 300,
};
const report: ChampionImpactReport = {
  schema_version: 1, state: "available", as_of: at, season_id: "season", profile_fingerprint: "profile", versions: { sizing: "size-v4" },
  since: "2026-09-13T07:00:00Z", window_size: 60, minimum_pairs: 30, minimum_coverage: 0.7, comparisons: [comparison],
};
function props() {
  return {
    learning: {
      mode: "active" as const, collecting_from_current_source: true, active_skill_versions: { sizing: "size-v4" }, champion_impact: structuredClone(report),
      champion_records: [{ skill: "sizing" as const, champion_version: "size-v4", champion_codename: "Quiet Balancer", champion_generation: 4, model_family: "linear" as const, recipe_version: null, crowned_at: null, retained_count: 2, inconclusive_count: 0, recorded_battle_count: 3, active: true, history_complete: true }],
    } as Pick<LearningStatus, "mode" | "collecting_from_current_source" | "active_skill_versions" | "champion_impact" | "champion_records" | "skills">,
    seasonId: "season", profile: "profile", serverTime: at,
  };
}

test("reports paired advantage in points even when both returns lose, with compact help", () => {
  const { container } = render(<ChampionImpact {...props()} />);
  expect(screen.getByText("Observed advantage")).toBeInTheDocument();
  expect(screen.getByText("-10.0%")).toBeInTheDocument();
  expect(screen.getByText("-5.0%")).toBeInTheDocument();
  expect(screen.getByText("+5.0 pp")).toBeInTheDocument();
  expect(screen.getByText(/45 usable \/ 60 resolved/)).toHaveTextContent("75.0% coverage · 3 pending");
  expect(screen.getByText("Quiet Balancer")).toBeInTheDocument();
  expect(screen.getByText("Sizing · v4")).toBeInTheDocument();
  expect(container.querySelector("details")).not.toHaveAttribute("open");
  expect(screen.getByLabelText("How Champion impact is measured")).toBeInTheDocument();
  expect(screen.getByText("Checkpoint comparison, not portfolio profit.")).toBeInTheDocument();
});

test.each(["collecting", "negative", "uncertain"] as const)("uses the reporting state %s without treating healthy as proof", state => {
  const value = props();
  value.learning.champion_impact!.comparisons[0]!.state = state;
  render(<ChampionImpact {...value} />);
  expect(screen.queryByText("Observed advantage")).not.toBeInTheDocument();
  expect(screen.getByText({ collecting: "Collecting comparisons", negative: "Observed disadvantage", uncertain: "No clear advantage" }[state])).toBeInTheDocument();
});

test.each(["season", "profile", "replacement", "stale", "future", "old-api", "invalid-number", "invalid-count"])("fails safely for %s", reason => {
  const value = props();
  if (reason === "season") value.seasonId = "new-season";
  if (reason === "profile") value.profile = "new-profile";
  if (reason === "replacement") value.learning.active_skill_versions = { sizing: "replacement" };
  if (reason === "stale") value.serverTime = "2026-09-13T10:03:00Z";
  if (reason === "future") value.serverTime = "2026-09-13T09:59:00Z";
  if (reason === "old-api") delete value.learning.champion_impact;
  if (reason === "invalid-number") value.learning.champion_impact!.comparisons[0]!.mean_advantage = NaN;
  if (reason === "invalid-count") value.learning.champion_impact!.comparisons[0]!.usable_count = 100;
  render(<ChampionImpact {...value} />);
  expect(screen.getByText("Waiting for current comparisons")).toBeInTheDocument();
  expect(screen.queryByText("+5.0 pp")).not.toBeInTheDocument();
});

test.each(["paused", "source", "suspended", "inactive"])("does not claim current influence when %s", reason => {
  const value = props();
  if (reason === "paused") value.learning.mode = "off";
  if (reason === "source") value.learning.collecting_from_current_source = false;
  if (reason === "suspended") value.learning.skills = [{ skill: "sizing", state: "suspended" } as ChallengerSkillStatus];
  if (reason === "inactive") value.learning.active_skill_versions = {};
  render(<ChampionImpact {...value} />);
  if (reason === "inactive") fireEvent.click(screen.getByRole("button", { name: "Sizing" }));
  expect(screen.queryByText("Observed advantage")).not.toBeInTheDocument();
  expect(screen.queryByText("+5.0 pp")).not.toBeInTheDocument();
});

test("Shadow after a new crown waits for activation without calling every skill paused", () => {
  const value = props();
  value.learning.mode = "shadow";
  value.learning.active_skill_versions = {};
  value.learning.champion_records![0] = { ...value.learning.champion_records![0]!, champion_version: "size-v5", champion_generation: 5, active: false };
  value.learning.skills = [{ skill: "sizing", state: "candidate_testing" }, { skill: "exit", state: "suspended" }] as ChallengerSkillStatus[];
  render(<ChampionImpact {...value} />);
  for (const name of ["Entry", "Manipulation", "Sizing"]) {
    fireEvent.click(screen.getByRole("button", { name }));
    expect(screen.getByText("Waiting for active support")).toBeInTheDocument();
    expect(screen.queryByText("Comparison paused")).not.toBeInTheDocument();
    expect(screen.queryByText("+5.0 pp")).not.toBeInTheDocument();
  }
  fireEvent.click(screen.getByRole("button", { name: "Exit" }));
  expect(screen.getByText("Support suspended")).toBeInTheDocument();
});

test.each(["sizing", "team"] as const)("Shadow cannot display retained %s results and resumes only with current activation", subject => {
  const value = props();
  if (subject === "team") {
    value.learning.active_skill_versions = { sizing: "size-v4", exit: "exit-v2" };
    value.learning.champion_impact!.versions = { ...value.learning.active_skill_versions };
    value.learning.champion_impact!.comparisons.push({ ...comparison, subject: "team" });
  }
  value.learning.mode = "shadow";
  const { rerender } = render(<ChampionImpact {...value} />);
  expect(screen.getByText("Waiting for active support")).toBeInTheDocument();
  expect(screen.queryByText("Observed advantage")).not.toBeInTheDocument();
  value.learning.mode = "active";
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByText("Observed advantage")).toBeInTheDocument();
  value.learning.mode = "shadow";
  value.learning.collecting_from_current_source = false;
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByText("Comparison paused")).toBeInTheDocument();
  expect(screen.queryByText("+5.0 pp")).not.toBeInTheDocument();
  value.learning.collecting_from_current_source = true;
  value.learning.mode = "off";
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByText("Comparison paused")).toBeInTheDocument();
});

test("a replacement crown never inherits the previous Champion's impact while waiting or activating", () => {
  const value = props();
  const { rerender } = render(<ChampionImpact {...value} />);
  expect(screen.getByText("+5.0 pp")).toBeInTheDocument();
  value.learning.mode = "shadow";
  value.learning.active_skill_versions = {};
  value.learning.champion_records![0] = { ...value.learning.champion_records![0]!, champion_version: "size-v5", champion_generation: 5, active: false };
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByRole("button", { name: "Sizing" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Waiting for active support")).toBeInTheDocument();
  expect(screen.queryByText("+5.0 pp")).not.toBeInTheDocument();
  expect(screen.queryByText("Sizing · v4")).not.toBeInTheDocument();

  value.learning.mode = "active";
  value.learning.active_skill_versions = { sizing: "size-v5" };
  value.learning.champion_records![0]!.active = true;
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByText("Waiting for current comparisons")).toBeInTheDocument();
  expect(screen.queryByText("+5.0 pp")).not.toBeInTheDocument();

  value.learning.champion_impact!.versions = { sizing: "size-v5" };
  value.learning.champion_impact!.since = at;
  value.learning.champion_impact!.comparisons = [{ ...comparison, state: "collecting", observed_count: 0, usable_count: 0, coverage: 0, reference_mean: null, supported_mean: null, mean_advantage: null, lower_bound: null, upper_bound: null, from: null, to: null }];
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByText("Collecting comparisons")).toBeInTheDocument();
  expect(screen.getByText("Sizing · v5")).toBeInTheDocument();
  expect(screen.getByText(/0 usable \/ 0 resolved/)).toHaveTextContent("3 pending");
  expect(screen.queryByText("Observed advantage")).not.toBeInTheDocument();
  expect(screen.getAllByText("—")).toHaveLength(3);
});

test("team displays the backend combination, allows selection, and clears stale results on removal", () => {
  const value = props();
  value.learning.active_skill_versions = { sizing: "size-v4", exit: "exit-v2" };
  value.learning.champion_impact!.versions = { ...value.learning.active_skill_versions };
  value.learning.champion_impact!.comparisons.push({ ...comparison, subject: "team", mean_advantage: 0.07 }, { ...comparison, subject: "exit", mean_advantage: 0.04 });
  const { rerender } = render(<ChampionImpact {...value} />);
  expect(screen.getByText("+7.0 pp")).toBeInTheDocument();
  expect(screen.queryByText("+9.0 pp")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Exit" }));
  expect(screen.getByText("+4.0 pp")).toBeInTheDocument();
  value.learning.active_skill_versions = { sizing: "size-v4" };
  rerender(<ChampionImpact {...value} />);
  expect(screen.getByText("Waiting for active support")).toBeInTheDocument();
  expect(screen.queryByText("+4.0 pp")).not.toBeInTheDocument();
});

test("pending-only evidence displays unknown values instead of zero returns", () => {
  const value = props();
  value.learning.champion_impact!.comparisons = [{ ...comparison, state: "collecting", observed_count: 0, usable_count: 0, coverage: 0, reference_mean: null, supported_mean: null, mean_advantage: null, lower_bound: null, upper_bound: null }];
  render(<ChampionImpact {...value} />);
  expect(screen.getAllByText("—")).toHaveLength(3);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

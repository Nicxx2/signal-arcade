import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import ArenaReadout from "./ArenaReadout";
import { battleReadout, edgeText, nextCheckText } from "./readout";
import { eventFixture, snapshotFixture } from "./fixtures";
import { viewForEvent, viewForSkill } from "./model";
import type { ArenaView } from "./model";

afterEach(cleanup);
const live = () => viewForSkill(snapshotFixture(), "entry")!;
const recap = (kind: "promoted" | "defended" | "inconclusive" | "first_champion") => viewForEvent(snapshotFixture(), eventFixture(kind));

test("the screenshot's exact tie keeps the Champion without claiming an advantage", () => {
  const view = { ...recap("defended"), mean: 0, lower: 0, usable: 30, observed: 31, coverage: 30 / 31 };
  render(<ArenaReadout view={view} stale />);
  expect(screen.getByRole("heading", { name: "Level result · Champion retained" })).toBeInTheDocument();
  expect(screen.getByText(/No measured advantage/)).toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAccessibleName(/average advantage 0.0 pp/);
  expect(document.querySelector(".ca-balance-marker")).toHaveStyle({ left: "50%" });
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByText(/It does not mean zero trading profit or missing data/)).toBeInTheDocument();
});

test("an exact mean tie can still have uncertainty and does not assert identical policies", () => {
  render(<ArenaReadout view={{ ...recap("defended"), mean: 0, lower: -.01, upper: .01 }} stale={false} />);
  expect(screen.getByRole("heading")).toHaveTextContent("Level result");
  expect(screen.getByText(/The band shows uncertainty/)).toBeInTheDocument();
  expect(screen.queryByText(/identical policies/)).toBeNull();
});

test("a zero-width saved interval is explained as a single point", () => {
  render(<ArenaReadout view={{ ...recap("defended"), mean: 0, lower: 0, upper: 0 }} stale={false} />);
  expect(screen.getByText(/uncertainty range is a single point/)).toBeInTheDocument();
});

test.each([null, .00001, -.00001])("missing or small signed values are not described as exact ties: %s", mean => {
  render(<ArenaReadout view={{ ...recap("defended"), mean, lower: -.01, upper: .01 }} stale={false} />);
  expect(screen.queryByText(/0.0 pp means the same measured average/)).toBeNull();
  expect(screen.getByRole("heading")).toHaveTextContent("Champion defended");
});

test("positive average with an inconclusive interval stays too close to call", () => {
  const view = live(); render(<ArenaReadout view={view} stale={false} />);
  expect(screen.getByRole("heading", { name: "Violet Pathfinder ahead on average" })).toBeInTheDocument();
  expect(screen.getByText(/Too close to call a safe replacement/)).toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAccessibleName(/uncertainty range −0.2 pp to \+5.0 pp/);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "35 of 30; evidence progress only");
});

test.each([
  [.01, .024, .05, "Violet Pathfinder has the edge"],
  [-.05, -.024, -.01, "Steady Sentinel has the edge"],
  [0, 0, 0, "Level so far"],
])("valid bounds name the leader without predicting a winner", (lower, mean, upper, title) => {
  const view = { ...live(), lower: Number(lower), mean: Number(mean), upper: Number(upper) };
  expect(battleReadout(view, false).title).toBe(title);
  expect(view.outcome).toBeNull();
});

test.each([
  { usable: 50, observed: 40 },
  { usable: 0, observed: 0 }, { lower: null }, { lower: .2, upper: .1 },
  { mean: Number.NaN }, { mean: Number.POSITIVE_INFINITY }, { mean: .2, upper: .1 },
  { mode: "interrupted" }, { paused: true },
] satisfies Partial<ArenaView>[])("insufficient or inconsistent evidence never positions a live advantage: %j", (patch) => {
  const view = { ...live(), ...patch };
  render(<ArenaReadout view={view} stale={false} />);
  expect(document.querySelector(".ca-balance-marker")).toBeNull();
  expect(screen.getByRole("img")).toHaveAccessibleName(/Advantage unavailable/);
  expect(screen.queryByText(/has the edge/)).toBeNull();
});

test("delayed updates retain measured advantage and progress without creating a result", () => {
  const view = { ...live(), lower: .01 };
  const mounted = render(<ArenaReadout view={view} stale={false} />);
  expect(screen.getByRole("heading")).toHaveTextContent("has the edge");
  mounted.rerender(<ArenaReadout view={view} stale />);
  expect(screen.getByRole("heading")).toHaveTextContent("ahead at the last update");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30");
  expect(document.querySelector(".ca-balance-marker")).not.toBeNull();
  expect(screen.getByRole("img")).toHaveAccessibleName(/Last received evidence/);
  mounted.rerender(<ArenaReadout view={view} stale={false} />);
  expect(screen.getByRole("heading")).toHaveTextContent("has the edge");
});

test("delayed first-Champion proof keeps the last received checks visible", () => {
  const view = { ...live(), mode: "training" as const, right: null, leftIsChampion: false,
    gates: [{ id: "a", label: "Coverage", state: "passed" }, { id: "b", label: "Independent proof", state: "not_met" }] as ArenaView["gates"] };
  render(<ArenaReadout view={view} stale />);
  expect(screen.getByRole("heading")).toHaveTextContent("Road to the first Champion");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  expect(screen.getByText("Last received evidence")).toBeInTheDocument();
  expect(screen.queryByText(/Waiting for fresh/)).toBeNull();
});

test("a delayed snapshot never fills in missing or mismatched evidence", () => {
  const view = { ...live(), lower: null };
  render(<ArenaReadout view={view} stale />);
  expect(document.querySelector(".ca-balance-marker")).toBeNull();
  expect(screen.getByRole("img")).toHaveAccessibleName(/Advantage unavailable/);
});

test("a saved defence with positive contender value explains that other checks prevented replacement", () => {
  render(<ArenaReadout view={recap("defended")} stale={false} />);
  expect(screen.getByText(/had a higher average, but did not prove/)).toBeInTheDocument();
  expect(screen.getByRole("heading")).toHaveTextContent("Champion defended");
});

test("a saved inconclusive result never invents a winner even with a positive mean", () => {
  render(<ArenaReadout view={recap("inconclusive")} stale={false} />);
  expect(screen.getByRole("heading")).toHaveTextContent("No replacement established");
  expect(document.querySelector(".ca-balance-range")).toBeNull();
});

test("values beyond the fixed scale clamp visually while preserving the real value", () => {
  render(<ArenaReadout view={{ ...recap("promoted"), mean: .3, lower: .2 }} stale={false} />);
  expect(document.querySelector(".ca-balance-marker")).toHaveStyle({ left: "100%" });
  expect(screen.getByRole("img")).toHaveAccessibleName(/\+30.0 pp.*beyond the displayed scale/);
});

test("missing historical metrics stay unknown while the saved result stays intact", () => {
  render(<ArenaReadout view={{ ...recap("promoted"), mean: null, lower: null }} stale />);
  expect(screen.getByRole("heading")).toHaveTextContent("New Champion crowned");
  expect(document.querySelector(".ca-balance-marker")).toBeNull();
});

test("first-Champion progress can regress and full checks do not invent a crown", () => {
  const view = { ...live(), mode: "training" as const, right: null, leftIsChampion: false, gates: [{ id: "a", label: "Coverage", state: "passed", detail: "Enough outcomes needed" }, { id: "b", label: "Independent proof", state: "not_met", detail: "A safe advantage is needed" }] as ArenaView["gates"] };
  const mounted = render(<ArenaReadout view={view} stale={false} />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  expect(screen.getByText("Independent proof")).toBeInTheDocument();
  mounted.rerender(<ArenaReadout view={{ ...view, gates: view.gates.map(g => ({ ...g, state: "passed" })) }} stale={false} />);
  expect(screen.getByText(/A recorded qualification result is still required/)).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  mounted.rerender(<ArenaReadout view={{ ...view, gates: view.gates.map(g => ({ ...g, state: "not_met" })) }} stale={false} />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
});

test("missing or mismatched first-Champion checks cannot appear complete", () => {
  const snapshot = snapshotFixture(), skill = snapshot.learning.skills![0]!;
  Object.assign(skill, { champion: null, testing_version: null, testing_candidate: null, gate_artifact_version: "old", gates: [{ state: "passed" }] });
  const view = viewForSkill(snapshot, "entry")!;
  render(<ArenaReadout view={view} stale={false} />);
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByText("Qualification checks are not available yet.")).toBeInTheDocument();
});

test("a first coronation needs no opponent, battle meter or invented qualification counts", () => {
  render(<ArenaReadout view={recap("first_champion")} stale />);
  expect(screen.getByRole("heading")).toHaveTextContent("First Champion crowned");
  expect(screen.getByText(/No opponent was needed/)).toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.queryByRole("img")).toBeNull();
});

test("tiny signed values stay distinct from exact zero and unknown", () => {
  expect(edgeText(0)).toBe("0.0 pp"); expect(edgeText(null)).toBe("Unknown");
  expect(edgeText(.00001)).toBe("+<0.01 pp"); expect(edgeText(-.00001)).toBe("−<0.01 pp");
});

test.each([
  { usable: 19, observed: 21, coverage: 19 / 21, mean: 0, lower: 0, upper: 0 },
  { usable: 1, observed: 1, coverage: 1, mean: .02, lower: .01, upper: .03 },
  { usable: 35, observed: 100, coverage: .35, mean: -.02, lower: -.03, upper: -.01 },
])("shows early or low-coverage averages as preliminary without weakening proof: %j", patch => {
  const view = { ...live(), ...patch };
  render(<ArenaReadout view={view} stale={false} />);
  expect(document.querySelector(".ca-balance-marker")).not.toBeNull();
  expect(screen.getByRole("img")).toHaveAccessibleName(/Preliminary evidence/);
  expect(screen.queryByText(/has the edge/)).toBeNull();
  expect(battleReadout(view, false).enough).toBe(false);
  expect(view.outcome).toBeNull();
  if (patch.mean === 0) expect(screen.getByRole("heading")).toHaveTextContent("Level so far");
});

test("the next first-Champion check explains the shortfall without backend jargon", () => {
  const gate = { id: "entry_policy_uplift_lower", label: "Conservative value", unit: "fraction", current: -.001, target: 0, comparison: ">", state: "not_met", detail: "Server-authoritative, chronological proof for this skill only." } as ArenaView["gates"][number];
  expect(nextCheckText(gate)).toBe("The evidence must support an improvement after costs. Current: −0.1 pp; required: > 0.0 pp.");
  expect(nextCheckText({ ...gate, label: "Executable coverage", current: .35, target: .7, comparison: ">=" })).toContain("Current: 35.0%; required: >= 70.0%.");
  expect(nextCheckText({ ...gate, unit: "boolean", current: false, target: true })).toBe("All qualification checks for this skill must pass together.");
  expect(nextCheckText({ ...gate, current: null })).toContain("Current: Unknown");
});

import { describe, expect, test } from "vitest";
import { contextFor, freshness, makeFighter, percentage, recordedDate, readQuality, resolveSelection, seedFor, viewForEvent, viewForSkill } from "./model";
import { eventFixture, snapshotFixture } from "./fixtures";

describe("authoritative arena mapping", () => {
  test("keeps active influence and the actual testing pair separate from the newest candidate", () => {
    const view = viewForSkill(snapshotFixture(), "entry")!;
    expect([view.mode, view.left?.id, view.left?.influence, view.right?.id]).toEqual(["battle", "champion", "Active", "candidate"]);
    expect(view.outcome).toBeNull();
  });
  test("does not invent a fighter for absent evidence", () => {
    const snapshot = snapshotFixture(); snapshot.learning.skills = [];
    expect(viewForSkill(snapshot, "entry")).toBeNull();
  });
  test("does not substitute a future contender for a missing testing artifact", () => {
    const snapshot = snapshotFixture(); snapshot.learning.skills![0]!.testing_candidate = null;
    expect(viewForSkill(snapshot, "entry")!.mode).toBe("interrupted");
    expect(viewForSkill(snapshot, "entry")!.right).toBeNull();
  });
  test("a malformed self-comparison cannot become a battle", () => {
    const snapshot = snapshotFixture(), skill = snapshot.learning.skills![0]!;
    skill.testing_version = skill.champion!.version; skill.testing_candidate = skill.champion;
    expect(viewForSkill(snapshot, "entry")!.mode).toBe("interrupted");
  });
  test("inconsistent observed and usable counts never direct provisional momentum", () => {
    const snapshot = snapshotFixture(); Object.assign(snapshot.learning.skills![0]!.tournament, { common_observed_count: 2, uplift_lower_bound: .01 });
    expect(viewForSkill(snapshot, "entry")!.momentum).toBe("neutral");
  });
  test("uses a training view before any Champion exists", () => {
    const snapshot = snapshotFixture(); Object.assign(snapshot.learning.skills![0]!, { champion: null, testing_version: null, testing_candidate: null, state: "collecting_proof" });
    expect(viewForSkill(snapshot, "entry")!.mode).toBe("training");
  });
  test.each([5, 29])("tiny samples cannot appear decisive (%i outcomes)", (count) => {
    const snapshot = snapshotFixture(); Object.assign(snapshot.learning.skills![0]!.tournament, { common_usable_count: count, uplift_lower_bound: .3, uplift_upper_bound: .4 });
    expect(viewForSkill(snapshot, "entry")!.momentum).toBe("neutral");
  });
  test.each([null, .69, Number.NaN, Number.POSITIVE_INFINITY])("missing/insufficient coverage keeps momentum neutral (%s)", (coverage) => {
    const snapshot = snapshotFixture(); Object.assign(snapshot.learning.skills![0]!.tournament, { availability_fraction: coverage, uplift_lower_bound: .2 });
    expect(viewForSkill(snapshot, "entry")!.momentum).toBe("neutral");
  });
  test("even a favourable bound never declares a winner", () => {
    const snapshot = snapshotFixture(); snapshot.learning.skills![0]!.tournament.uplift_lower_bound = .02;
    const view = viewForSkill(snapshot, "entry")!;
    expect(view.momentum).toBe("right"); expect(view.outcome).toBeNull();
  });
  test("malformed or mismatched tournament metrics cannot direct a fight", () => {
    const snapshot = snapshotFixture(); Object.assign(snapshot.learning.skills![0]!.tournament, { candidate_version: "old-candidate", mean_uplift: 99 });
    const view = viewForSkill(snapshot, "entry")!;
    expect(view.mean).toBeNull(); expect(view.momentum).toBe("neutral");
  });
  test.each(["entry", "manipulation", "sizing", "exit"] as const)("suspended %s support does not pause a current shadow comparison", (skill) => {
    const snapshot = snapshotFixture(); Object.assign(snapshot.learning.skills![0]!, { skill, state: "suspended", active_version: null });
    snapshot.learning.skills![0]!.tournament.uplift_lower_bound = .02;
    const view = viewForSkill(snapshot, skill)!;
    expect(view.paused).toBe(false); expect(view.momentum).toBe("right");
    expect(view.left?.influence).toBe("Suspended");
    expect(view.mode).toBe("battle"); expect(view.outcome).toBeNull();
  });
  test.each(["off", "source"])("a real %s pause still stops live choreography", (reason) => {
    const snapshot = snapshotFixture();
    if (reason === "off") snapshot.learning.mode = "off";
    else snapshot.learning.collecting_from_current_source = false;
    const view = viewForSkill(snapshot, "entry")!;
    expect(view.paused).toBe(true); expect(view.momentum).toBe("neutral");
  });
  test("matches a completed pair after the next contender starts", () => {
    const snapshot = snapshotFixture(), initial = viewForSkill(snapshot, "entry")!;
    snapshot.learning.champion_journey = [eventFixture()];
    const status = snapshot.learning.skills![0]!;
    status.champion = status.testing_candidate!; status.testing_version = "future"; status.testing_candidate = status.latest_candidate;
    const view = resolveSelection(snapshot, { context: contextFor(snapshot), initial })!;
    expect(view.mode).toBe("recap"); expect(view.left?.id).toBe("champion"); expect(view.right?.id).toBe("candidate");
  });
  test("disappearance without a saved result is an interruption", () => {
    const snapshot = snapshotFixture(), initial = viewForSkill(snapshot, "entry")!;
    snapshot.learning.skills![0]!.testing_version = null;
    expect(resolveSelection(snapshot, { context: contextFor(snapshot), initial })!.mode).toBe("interrupted");
  });
  test.each(["risk", "source", "cohort"])("old requests cannot cross a %s change", (change) => {
    const snapshot = snapshotFixture(), selection = { context: contextFor(snapshot), initial: viewForSkill(snapshot, "entry")! };
    if (change === "risk") snapshot.risk_mode = "safe";
    if (change === "source") snapshot.demo_mode = true;
    if (change === "cohort") snapshot.learning.champion_journey_cohort_key = "new-config";
    expect(resolveSelection(snapshot, selection)).toBeNull();
  });
  test("a same-cohort season rollover does not create a new battle", () => {
    const snapshot = snapshotFixture(), selection = { context: contextFor(snapshot), initial: viewForSkill(snapshot, "entry")! };
    snapshot.started_at = "2026-09-04T12:11:00Z";
    expect(resolveSelection(snapshot, selection)!.key).toBe(selection.initial.key);
  });
  test("founder coronation never invents an opponent", () => {
    const view = viewForEvent(snapshotFixture(), eventFixture("first_champion"));
    expect(view.left?.id).toBe("candidate"); expect(view.right).toBeNull();
  });
  test.each(["defended", "inconclusive"] as const)("preserves %s without reversing the contender's metric", (kind) => {
    const view = viewForEvent(snapshotFixture(), eventFixture(kind));
    expect(view.outcome).toBe(kind); expect(view.mean).toBe(.034); expect(view.momentum).toBe("neutral");
  });
  test("a frozen recap keeps its opponent and metrics while influence updates", () => {
    const snapshot = snapshotFixture(), initial = viewForEvent(snapshot, eventFixture());
    const selection = { context: contextFor(snapshot), initial };
    snapshot.learning.skills![0]!.active_version = "candidate";
    snapshot.learning.skills![0]!.tournament.mean_uplift = .9;
    const view = resolveSelection(snapshot, selection)!;
    expect(view.mean).toBe(.034); expect(view.right?.influence).toBe("Active now");
  });
});

test("cached snapshots do not become fresh just because server time advanced", () => {
  const snapshot = snapshotFixture(); snapshot.server_time = "2026-09-04T12:11:00Z";
  expect(freshness(snapshot, 3)).toBe(63);
});
test.each([undefined, "invalid", "2026-09-04T13:00:00Z"])("uncertain provenance fails closed: %s", (date) => {
  const snapshot = snapshotFixture(); snapshot.snapshot_generated_at = date;
  expect(freshness(snapshot, 0)).toBeNull();
});
test("cosmetic identity is stable and full identity is retained even for duplicate names", () => {
  expect(seedFor("hello")).toBe(1335831723);
  const left = makeFighter("a", "Steady Sentinel", "linear", "entry");
  expect(makeFighter("a", "Steady Sentinel", "linear", "entry")).toEqual(left);
  const right = makeFighter("b", "Steady Sentinel", "linear", "entry");
  expect(left.id).not.toBe(right.id); expect(left.signature).not.toBe(right.signature);
});

test("a newer candidate does not redraw the selected candidate or pretend a battle ended", () => {
  const snapshot = snapshotFixture(), status = snapshot.learning.skills![0]!;
  Object.assign(status, { champion: null, testing_version: null, testing_candidate: null });
  const initial = viewForSkill(snapshot, "entry")!;
  status.latest_candidate = { ...status.latest_candidate!, version: "new-generation", codename: initial.left!.name };
  snapshot.snapshot_generated_at = "2026-09-04T12:20:00Z";
  const selected = resolveSelection(snapshot, { context: contextFor(snapshot), initial })!;
  expect(selected.mode).toBe("training");
  expect(selected.superseded).toBe(true);
  expect(selected.left).toEqual(initial.left);
  expect(selected.outcome).toBeNull();
  expect(selected.evidenceAt).toBe("2026-09-04T12:10:00Z");
  expect(selected.detail).not.toMatch(/pair|battle|winner/);
  expect(viewForSkill(snapshot, "entry")!.left?.signature).not.toBe(initial.left!.signature);
});

test("an opened contender can become the first Champion without acquiring an invented opponent", () => {
  const snapshot = snapshotFixture(), status = snapshot.learning.skills![0]!;
  Object.assign(status, { champion: null, testing_version: null, testing_candidate: null });
  const initial = viewForSkill(snapshot, "entry")!;
  status.champion = status.latest_candidate;
  const selected = resolveSelection(snapshot, { context: contextFor(snapshot), initial })!;
  expect(selected.mode).toBe("champion");
  expect(selected.left?.id).toBe(initial.left?.id);
  expect(selected.right).toBeNull();
  expect(selected.superseded).not.toBe(true);
});

test("an open Champion profile stays that fighter when its next battle starts", () => {
  const snapshot = snapshotFixture(), status = snapshot.learning.skills![0]!;
  status.testing_version = null;
  const initial = viewForSkill(snapshot, "entry")!;
  status.testing_version = status.testing_candidate!.version;
  const selected = resolveSelection(snapshot, { context: contextFor(snapshot), initial })!;
  expect(selected.mode).toBe("champion");
  expect(selected.left).toEqual(initial.left);
  expect(selected.right).toBeNull();
  expect(selected.detail).toContain("Select Entry above to watch");
  expect(viewForSkill(snapshot, "entry")!.mode).toBe("battle");
});

test("a replaced Champion profile keeps its identity without claiming the current crown", () => {
  const snapshot = snapshotFixture(), status = snapshot.learning.skills![0]!;
  status.testing_version = null;
  const initial = viewForSkill(snapshot, "entry")!;
  status.champion = status.latest_candidate;
  const selected = resolveSelection(snapshot, { context: contextFor(snapshot), initial })!;
  expect(selected.mode).toBe("champion");
  expect(selected.left).toEqual(initial.left);
  expect(selected.superseded).toBe(true);
  expect(selected.title).toBe("Saved Champion profile");
  expect(selected.outcome).toBeNull();
});
test("unknown values are not formatted as profit or zero", () => { expect(percentage(null)).toBe("Unknown"); expect(percentage(.017, true)).toBe("+1.7 pp"); });
test.each([undefined, "invalid"])("missing recap dates stay unknown: %s", (date) => { expect(recordedDate(date)).toBe("Recorded date unavailable"); });
test("corrupt graphics preferences use safe defaults", () => {
  localStorage.setItem("signal-arcade-champion-graphics-v1", "turbo"); expect(readQuality()).toBe("auto"); localStorage.clear();
});

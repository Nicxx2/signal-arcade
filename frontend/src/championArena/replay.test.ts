import { describe, expect, test } from "vitest";
import { replayFixture, snapshotFixture } from "./fixtures";
import { viewForEvent } from "./model";
import { replayFrame, replayTrail, validateReplay } from "./replay";
import { battleReadout } from "./readout";

describe("recorded battle evidence", () => {
  test("preserves two ordered checkpoints recorded within the same millisecond", () => {
    const { event, response } = replayFixture();
    response.timeline!.points[0]!.at = "2026-09-04T12:00:00.123001+00:00";
    response.timeline!.points[1]!.at = "2026-09-04T12:00:00.123002+00:00";
    expect(validateReplay(response, event, response.cohort_key)).not.toBeNull();
    response.timeline!.points[1]!.at = "2026-09-04T12:00:00.123000+00:00";
    expect(validateReplay(response, event, response.cohort_key)).toBeNull();
  });
  test("shows exact changes, requires evidence, and reveals the recorded winner only at the end", () => {
    const { event, response } = replayFixture(), base = viewForEvent(snapshotFixture(), event);
    const timeline = validateReplay(response, event, response.cohort_key)!;
    const frames = timeline.points.map((_, index) => replayFrame(base, timeline, index));
    expect(frames.map(view => view.mean)).toEqual([null, .03, -.01, -.035]);
    expect(frames.map(view => view.outcome)).toEqual([null, null, null, "defended"]);
    expect(frames.map(view => view.key)).toEqual(Array(4).fill(base.key));
    expect(battleReadout(frames[0]!, false).plot).toBe(false);
    expect(battleReadout(frames[1]!, true).plot).toBe(true); // Saved data does not expire with the market snapshot.
    expect(battleReadout(frames[1]!, false).title).toBe("Violet Pathfinder ahead on average");
    expect(battleReadout(frames[3]!, false).title).toBe("Champion defended the crown");
    expect(frames[0]!.title).not.toBe(base.title);
  });
  test("a level defence remains level at every recorded comparison", () => {
    const { event, response } = replayFixture();
    response.timeline!.points.forEach(point => { point.mean = point.lower = point.upper = 0; });
    event.mean_uplift = event.uplift_lower_bound = 0;
    const timeline = validateReplay(response, event, response.cohort_key)!;
    expect(timeline).not.toBeNull();
    expect(timeline.points.map((_, index) => replayFrame(viewForEvent(snapshotFixture(), event), timeline, index).momentum)).toEqual(Array(4).fill("neutral"));
  });
  test("the reported 19-to-30-outcome replay shows level measurements before qualification", () => {
    const { event, response } = replayFixture();
    const t = response.timeline!;
    t.points.forEach((p, i) => { p.usable = 19 + i; p.observed = 21 + i; p.coverage = p.usable / p.observed; p.mean = p.lower = p.upper = 0; });
    const view = replayFrame(viewForEvent(snapshotFixture(), event), t, 1);
    expect(battleReadout(view, false)).toMatchObject({ title: "Level so far", plot: true, preliminary: true, evidenceText: "20 usable · preliminary" });
    expect(view.momentum).toBe("neutral"); expect(view.outcome).toBeNull();
    expect(replayTrail(t, 1).summary).toBe("Level in every measured checkpoint shown.");
  });
  test("the bounded trail hides future turns, preserves gaps and clips only coordinates", () => {
    const { response } = replayFixture(), t = response.timeline!;
    expect(replayTrail(t, 1).dots).toHaveLength(2);
    expect(replayTrail(t, 1).summary).not.toContain("Both sides");
    expect(replayTrail(t, 2).summary).toContain("Both sides");
    t.points[1]!.mean = t.points[1]!.lower = t.points[1]!.upper = .5;
    expect(replayTrail(t, 1).dots[1]).toMatchObject({ mean: .5, y: 12 });
    t.points[2]!.mean = t.points[2]!.lower = t.points[2]!.upper = null;
    expect(replayTrail(t, 3).dots[2]).toBeNull();
    expect(replayTrail(t, 3).hasGap).toBe(true);
  });
  test.each(["pair", "cohort", "event", "skill", "order", "date", "zone", "coverage", "count", "booleanCount", "bounds", "nonfinite", "missingMean", "final", "tooLarge", "onePoint", "flags", "minimum", "first"])("rejects %s without borrowing another battle's history", damage => {
    const { event, response } = replayFixture(), t = response.timeline!, p = t.points[1]!;
    if (damage === "pair") t.candidate_version = "another";
    if (damage === "cohort") t.cohort_key = "another";
    if (damage === "event") response.event_id = "another";
    if (damage === "skill") t.skill = "exit";
    if (damage === "order") p.sequence = 0;
    if (damage === "date") p.at = "invalid";
    if (damage === "zone") p.at = "2026-09-04T12:05:00";
    if (damage === "coverage") p.coverage = .9;
    if (damage === "count") p.usable = 50;
    if (damage === "booleanCount") Object.assign(p, { usable: true });
    if (damage === "bounds") p.lower = .5;
    if (damage === "nonfinite") p.mean = Infinity;
    if (damage === "missingMean") Object.assign(p, { mean: undefined });
    if (damage === "final") event.mean_uplift = .03;
    if (damage === "tooLarge") t.points = Array(33).fill(p);
    if (damage === "onePoint") t.points = t.points.slice(-1);
    if (damage === "flags") Object.assign(t, { partial: "false" });
    if (damage === "minimum") t.minimum_coverage = 0;
    if (damage === "first") event.kind = "first_champion";
    expect(validateReplay(response, event, response.cohort_key)).toBeNull();
  });
  test("missing history stays final-only, while partial/sampled recordings keep their labels", () => {
    const { event, response } = replayFixture();
    expect(validateReplay({ ...response, timeline: null }, event, response.cohort_key)).toBeNull();
    response.timeline!.partial = response.timeline!.sampled = true;
    expect(validateReplay(response, event, response.cohort_key)).toEqual(response.timeline);
  });
});

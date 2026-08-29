import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Decisions } from "./App";
import { organizeDecisions } from "./decisionView";
import type { Decision, DecisionAction } from "./types";

function makeDecision(
  id: string,
  mint: string,
  symbol: string,
  action: DecisionAction,
  score: number,
  createdAt: string,
): Decision {
  return {
    decision_id: id,
    mint,
    symbol,
    created_at: createdAt,
    action,
    risk_mode: "balanced",
    score: {
      opportunity: 0.7,
      danger: 0.2,
      execution: 0.6,
      confidence: 0.8,
      net_edge_index: 0.02,
      composite: score,
    },
    reasons: ["Test evidence"],
    blockers: action === "pass" ? ["test_blocker"] : [],
    feature_snapshot: {
      mint,
      symbol,
      name: symbol,
      venue: "pump",
      computed_at: createdAt,
      values: {
        market_freshness: {
          value: 0,
          unit: "seconds",
          as_of: createdAt,
          sources: ["test"],
          freshness_seconds: 0,
          quality: 1,
          missing_reason: null,
        },
      },
      data_confidence: 0.8,
      hard_flags: [],
    },
    model_version: "test",
    season_id: "season-test",
    configuration_fingerprint: "config-test",
    planned_order_size_sol: 0.025,
    learning_assessment: null,
  };
}

const earlier = makeDecision("aaa-old", "mint-aaa", "AAA", "watch", 76, "2026-01-01T00:00:00Z");
const latest = makeDecision("aaa-new", "mint-aaa", "AAA", "pass", 42, "2026-01-01T00:01:00Z");
const best = makeDecision("bbb-new", "mint-bbb", "BBB", "enter", 84, "2026-01-01T00:02:00Z");
const timing = {
  asOfMs: Date.parse("2026-01-01T00:02:00Z"),
  candidateWindowMinutes: 30,
  staleMarketSeconds: 120,
};

afterEach(cleanup);

test("shows only the latest token state in ranked and passed groups", () => {
  const groups = organizeDecisions([earlier, latest, best], timing);
  expect(groups.best.map((decision) => decision.decision_id)).toEqual(["bbb-new"]);
  expect(groups.passed.map((decision) => decision.decision_id)).toEqual(["aaa-new"]);
  expect(groups.earlier.map((decision) => decision.decision_id)).toEqual([]);
});

test("moves stale opportunities and invalid timestamps out of the current ranking", () => {
  const stale = makeDecision("stale", "mint-stale", "STALE", "watch", 90, "2026-01-01T00:00:00Z");
  const invalid = makeDecision("invalid", "mint-invalid", "INVALID", "enter", 99, "not-a-date");
  const missingFreshness = {
    ...best,
    decision_id: "missing-freshness",
    mint: "mint-missing",
    symbol: "MISSING",
    feature_snapshot: { ...best.feature_snapshot, mint: "mint-missing", values: {} },
  };
  const groups = organizeDecisions([stale, invalid, missingFreshness], {
    ...timing,
    staleMarketSeconds: 20,
  });

  expect(groups.best).toEqual([]);
  expect(groups.earlier.map((decision) => decision.decision_id)).toEqual([
    "missing-freshness",
    "stale",
    "invalid",
  ]);
});

test("explains where live candidates went when no best signal is currently safe", () => {
  const explain = vi.fn().mockResolvedValue(undefined);
  const passed = makeDecision(
    "passed-now",
    "mint-passed",
    "PASSED",
    "abstain",
    62,
    "2026-01-01T00:02:00Z",
  );
  render(<Decisions decisions={[passed]} explain={explain} serverTime="2026-01-01T00:02:01Z" candidateWindowMinutes={30} staleMarketSeconds={120} />);

  expect(screen.getByText(/1 latest candidate is safely shown in Passed for now/i)).toBeInTheDocument();
});

test("renders malformed decision timestamps without leaking NaN into the UI", () => {
  const explain = vi.fn().mockResolvedValue(undefined);
  const invalid = makeDecision("invalid-time", "mint-invalid", "INVALID", "watch", 70, "not-a-date");
  render(<Decisions decisions={[invalid]} explain={explain} serverTime="2026-01-01T00:02:00Z" candidateWindowMinutes={30} staleMarketSeconds={120} />);

  fireEvent.click(screen.getByRole("button", { name: /Expired from current view/i }));
  expect(screen.getByText(/time unknown/)).toBeInTheDocument();
  expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
});

test("explains that an old 15-second history gate was true only at its checkpoint", () => {
  const explain = vi.fn().mockResolvedValue(undefined);
  const young = {
    ...makeDecision("young", "mint-young", "YOUNG", "pass", 55, "2026-01-01T00:00:00Z"),
    blockers: ["needs_at_least_15_seconds_of_history"],
    feature_snapshot: {
      ...makeDecision("young", "mint-young", "YOUNG", "pass", 55, "2026-01-01T00:00:00Z").feature_snapshot,
      values: {
        market_freshness: makeDecision("young", "mint-young", "YOUNG", "pass", 55, "2026-01-01T00:00:00Z").feature_snapshot.values.market_freshness!,
        age_seconds: {
          value: 8, unit: "seconds", as_of: "2026-01-01T00:00:00Z", sources: ["test"], freshness_seconds: 0, quality: 1, missing_reason: null,
        },
      },
    },
  };
  render(<Decisions decisions={[young]} explain={explain} serverTime="2026-01-01T00:03:00Z" candidateWindowMinutes={30} staleMarketSeconds={20} />);

  fireEvent.click(screen.getByRole("button", { name: /Passed for now/i }));
  fireEvent.click(screen.getByRole("button", { name: "Review YOUNG decision details" }));
  expect(screen.getByText(/That time gate has since matured/)).toBeInTheDocument();
});

test("pauses only the visible journal while new decisions continue arriving", () => {
  const explain = vi.fn().mockResolvedValue(undefined);
  const view = render(<Decisions decisions={[earlier]} explain={explain} serverTime="2026-01-01T00:02:00Z" candidateWindowMinutes={30} staleMarketSeconds={120} />);
  fireEvent.click(screen.getByRole("button", { name: "Pause view" }));

  view.rerender(<Decisions decisions={[best, earlier]} explain={explain} serverTime="2026-01-01T00:02:10Z" candidateWindowMinutes={30} staleMarketSeconds={120} />);
  expect(screen.queryByText("BBB")).not.toBeInTheDocument();
  expect(screen.getByText("AAA")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Resume live · 1 new" })).toBeInTheDocument();
  expect(screen.getByText("Your view is frozen; analysis and paper trading continue.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Resume live · 1 new" }));
  expect(screen.getByText("BBB")).toBeInTheDocument();
});

test("freezes the view while reviewing details and closes the review on resume", () => {
  const explain = vi.fn().mockResolvedValue(undefined);
  render(<Decisions decisions={[best]} explain={explain} serverTime="2026-01-01T00:02:00Z" candidateWindowMinutes={30} staleMarketSeconds={120} />);

  expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review BBB decision details" }));

  expect(screen.getByRole("button", { name: "Resume live" })).toBeInTheDocument();
  expect(screen.getByText("Paper enter")).toBeInTheDocument();
  expect(screen.getByText("Evidence")).toBeInTheDocument();
  expect(screen.getByText(/edge index ranks evidence.*not a profit forecast/i)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "BBB mint address" })).toHaveValue("mint-bbb");
  expect(screen.getByText(/GMGN is an external research\/trading site/)).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Open BBB on GMGN" }).some((link) => link.getAttribute("href") === "https://gmgn.ai/sol/token/mint-bbb")).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: "Resume live" }));
  expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
});

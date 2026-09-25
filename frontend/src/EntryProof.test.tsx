import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import EntryProof from "./EntryProof";
import { entryProofSummary } from "./entryProofModel";
import { artifact, snapshotFixture } from "./championArena/fixtures";
import type { LearningStatus, ReadinessGate } from "./types";

afterEach(cleanup);
const gate = (id: string, state: ReadinessGate["state"] = "passed"): ReadinessGate => ({ id, label: id, state, current: state === "passed", target: true, comparison: "=", unit: "boolean", detail: "Saved evidence" });
const renderGates = (gates: ReadinessGate[]) => <ul>{gates.map(g => <li key={g.id}>{g.label}: {g.current === null ? "Unknown" : String(g.current)}</li>)}</ul>;
function learning(): LearningStatus {
  const champion = { version: "older-xgb", codename: "Saved Beacon", model_family: "xgboost" };
  return { ...snapshotFixture().learning, mode: "shadow", activation_available: true, skills: [], entry_proof: {
    version: "entry-proof-v1",
    families: [
      { family: "linear", artifact: artifact("latest-linear", "Linear Scout"), state: "proof_not_met", gates: [gate("Linear validation", "not_met")] },
      { family: "xgboost", artifact: { ...artifact("newer-xgb", "Nonlinear Beacon"), model_family: "xgboost" }, state: "proof_not_met", gates: [gate("XGBoost validation"), gate("Paired Linear improvement", "not_met")] },
    ],
    activation: { champion, subject: champion, source: "skill_champion", ready: true, active: null, consent_granted: false, gates: [gate("Current coverage")] },
  } };
}
const show = (value = learning()) => render(<EntryProof learning={value} renderGates={renderGates} />);

const coverage = { schema: 1, resolved: 1000, usable: 430, quote_liquidity: 305, quote_fees: 8, quote_other: 0, stale_route: 251, window_elapsed: 6, other_missing: 0 };

test.each([[undefined, "70%"], [0.65, "65%"], [0.55, "55%"], [null, "unknown"]] as const)("fitted proof uses its recorded requirement: %s", (minimum, expected) => {
  const value = learning();
  value.challenger_minimum_availability = .6;
  const model = value.entry_proof!.families[0]!.artifact!;
  model.coverage_breakdown = coverage; model.sample_count = 430; model.metrics.outcome_availability = .43;
  model.minimum_outcome_coverage = minimum;
  show(value);
  expect(screen.getByText(/The requirement for this generation/)).toHaveTextContent(`requirement for this generation is ${expected}.`);
});

test("coverage counts belong to each fitted generation and never borrow current collection", () => {
  const value = learning();
  const linear = value.entry_proof!.families[0]!.artifact!;
  const xgb = value.entry_proof!.families[1]!.artifact!;
  linear.coverage_breakdown = coverage; linear.sample_count = 430; linear.metrics.outcome_availability = .43;
  xgb.coverage_breakdown = { ...coverage, usable: 425, other_missing: 5 }; xgb.sample_count = 425; xgb.metrics.outcome_availability = .425;
  show(value);
  const linearPanel = screen.getByText("Linear proof").closest("details")!;
  const xgbPanel = screen.getByText("XGBoost proof").closest("details")!;
  expect(within(linearPanel).getByText("430 / 1,000 usable outcomes · 43.0%")).toBeInTheDocument();
  expect(within(xgbPanel).getByText("425 / 1,000 usable outcomes · 42.5%")).toBeInTheDocument();
  expect(within(linearPanel).getByText("Quote failed: insufficient real reserves: 305")).toBeInTheDocument();
  expect(within(linearPanel).getByText(/missed checkpoints are not guaranteed recoverable/)).toBeInTheDocument();
  expect(within(xgbPanel).getByText("1 / 2 checks passing")).toBeInTheDocument();
});

test.each([undefined, null, {}, { ...coverage, schema: 2 }, { ...coverage, usable: 429 }, { ...coverage, other_missing: 1 }, { ...coverage, quote_fees: -8 }, { ...coverage, quote_fees: "8" }, { ...coverage, resolved: 0 }])("missing or invalid cohort metadata stays unknown: %j", report => {
  const value = learning();
  const model = value.entry_proof!.families[0]!.artifact!;
  model.sample_count = 430; model.metrics.outcome_availability = .43;
  model.coverage_breakdown = report as typeof model.coverage_breakdown;
  show(value);
  expect(screen.getAllByText("Coverage breakdown unavailable for this generation.")).toHaveLength(2);
  expect(screen.queryByRole("region", { name: "Fitted cohort coverage" })).toBeNull();
  expect(screen.getByText("Linear validation: false")).toBeInTheDocument();
});

test.each([undefined, null])("an incomplete artifact with missing metrics keeps its gates readable: %j", metrics => {
  const value = learning();
  const model = value.entry_proof!.families[0]!.artifact!;
  model.sample_count = 430; model.coverage_breakdown = coverage;
  model.metrics = metrics as unknown as typeof model.metrics;
  show(value);
  expect(screen.getAllByText("Coverage breakdown unavailable for this generation.")).toHaveLength(2);
  expect(screen.getByText("Linear validation: false")).toBeInTheDocument();
});

test("family evidence stays with its named generation while activation uses the older Champion", () => {
  show();
  const linear = screen.getByText("Linear proof").closest("details")!;
  const xgb = screen.getByText("XGBoost proof").closest("details")!;
  expect(within(linear).getByText("Linear validation: false")).toBeInTheDocument();
  expect(within(linear).queryByText(/XGBoost validation/)).toBeNull();
  expect(within(linear).getByText("0 / 1 checks passing")).toBeInTheDocument();
  expect(within(xgb).getByText("1 / 2 checks passing")).toBeInTheDocument();
  const activation = screen.getByRole("region", { name: "Entry activation readiness" });
  expect(within(activation).getByText("Ready for activation")).toBeInTheDocument();
  expect(within(activation).getByTitle("older-xgb")).toHaveTextContent("Saved Beacon · XGBoost");
  expect(within(activation).queryByText("Nonlinear Beacon")).toBeNull();
  expect(within(activation).getByText(/Consent has not been granted/)).toBeInTheDocument();
  expect(screen.getByText(/Linear or XGBoost can earn the first crown/)).toBeInTheDocument();
  expect(linear).not.toHaveAttribute("open");
  expect(xgb).not.toHaveAttribute("open");
});

test("missing or mismatched family data never borrows the other model's gates", () => {
  const value = learning();
  value.entry_proof!.families = [{ ...value.entry_proof!.families[0]!, artifact: { ...artifact("wrong"), model_family: "xgboost" } }];
  show(value);
  expect(screen.getAllByText("No fitted artifact yet")).toHaveLength(2);
  expect(screen.queryByText(/Linear validation/)).toBeNull();
});

test.each([
  ["off", true, "Learning paused"],
  ["active", false, "Saved proof · source separate"],
] as const)("mode %s and source %s cannot claim current influence", (mode, source, summary) => {
  const value = learning(); value.mode = mode; value.collecting_from_current_source = source;
  value.entry_proof!.activation.active = value.entry_proof!.activation.champion;
  show(value);
  expect(entryProofSummary(value)).toBe(summary);
  expect(screen.queryByText(/Influencing entries/)).toBeNull();
});

test("consent alone cannot make a suspended or unready Champion active", () => {
  const value = learning(); value.activation_available = false;
  value.entry_proof!.activation.ready = false; value.entry_proof!.activation.consent_granted = true;
  show(value);
  expect(screen.getByText("Champion saved · activation gated")).toBeInTheDocument();
  expect(screen.getByText(/Consent was previously granted/)).toBeInTheDocument();
  expect(screen.queryByText(/Influencing entries/)).toBeNull();
});

test("legacy fallback identifies Linear diagnostics without calling them XGBoost proof", () => {
  const value = learning(); delete value.entry_proof;
  value.qualification_gates = [gate("Older shared check")];
  show(value);
  expect(screen.getByText("Legacy Linear diagnostics")).toBeInTheDocument();
  expect(screen.getByText(/not the XGBoost candidate’s checklist/)).toBeInTheDocument();
  expect(screen.queryByText("XGBoost proof")).toBeNull();
});

test("no Champion and an eligible legacy model remain distinct", () => {
  const value = learning(); const activation = value.entry_proof!.activation;
  activation.champion = null; activation.subject = { version: "legacy", codename: "Legacy Linear model", model_family: "linear" }; activation.source = "legacy_linear";
  show(value);
  expect(screen.getByText(/No Entry Champion has been recorded/)).toBeInTheDocument();
  expect(screen.getByText(/Legacy activation candidate/)).toBeInTheDocument();
  expect(screen.getByTitle("legacy")).toHaveTextContent("Legacy Linear model · Linear");
});

test("unknown historical evidence is presented as unknown", () => {
  const value = learning(); value.entry_proof!.families[0]!.gates = [{ ...gate("Familiar evidence", "collecting"), current: null, target: null }];
  show(value);
  expect(screen.getByText("Familiar evidence: Unknown")).toBeInTheDocument();
});

test.each([
  { version: "entry-proof-v2" },
  { version: "entry-proof-v1", families: [] },
  { version: "entry-proof-v1", families: null, activation: { gates: [] } },
  { version: "entry-proof-v1", families: [], activation: { gates: null } },
])("unsupported or incomplete report envelopes fall back without breaking Learning: %j", proof => {
  const value = learning(); value.activation_available = false;
  value.entry_proof = proof as unknown as LearningStatus["entry_proof"];
  show(value);
  expect(screen.getByText("Legacy Linear diagnostics")).toBeInTheDocument();
  expect(screen.queryByText("XGBoost proof")).toBeNull();
  expect(entryProofSummary(value)).toBe("First Entry Champion pending");
});

test("unsupported report versions cannot contribute a phantom Champion to the summary", () => {
  const value = learning(); value.activation_available = false;
  value.entry_proof = { ...value.entry_proof!, version: "entry-proof-v2" } as unknown as LearningStatus["entry_proof"];
  expect(entryProofSummary(value)).toBe("First Entry Champion pending");
});

test.each(["sizing", "exit"] as const)("active %s cannot claim that Entry is influencing decisions", skill => {
  const value = learning();
  value.mode = "active";
  value.auto_participation = true;
  value.active_skill_versions = { [skill]: `${skill}-champion` };
  value.activation_available = false;
  value.entry_proof!.activation = { ...value.entry_proof!.activation, champion: null, subject: null, active: null, ready: false };
  show(value);
  expect(entryProofSummary(value)).toBe("First Entry Champion pending");
  expect(screen.queryByText("Entry influence active")).toBeNull();
  expect(screen.queryByText(/Influencing entries/)).toBeNull();
  expect(screen.getByText(/Automatic support is allowed/)).toBeInTheDocument();
  expect(screen.queryByText(/Consent has not been granted/)).toBeNull();
  delete value.entry_proof;
  expect(entryProofSummary(value)).toBe("First Entry Champion pending");
});

test("a confirmed active Entry remains distinct from another active skill", () => {
  const value = learning();
  value.mode = "active";
  value.entry_proof!.activation.active = value.entry_proof!.activation.champion;
  show(value);
  expect(entryProofSummary(value)).toBe("Entry influence active");
  expect(screen.getByText(/Influencing entries/)).toBeInTheDocument();
});

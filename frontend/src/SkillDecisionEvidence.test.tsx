import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import SkillDecisionEvidence from "./SkillDecisionEvidence";
import type { DecisionSkillReceipt } from "./types";

afterEach(cleanup);
const receipt = (patch: Partial<DecisionSkillReceipt> = {}): DecisionSkillReceipt => ({ artifact_version: "saved-champion", skill: "manipulation", evaluated_at: "2026-09-20T10:00:00Z", prediction: -0.2, conservative_value: -0.25, in_distribution: true, proposed_action: "veto", baseline_actionable: true, parameters: { applied: true }, ...patch });
const show = (value: DecisionSkillReceipt) => render(<SkillDecisionEvidence assessments={{ manipulation: value }} />);

test("applied veto is distinct from an unsupported proposal and from a fill", () => {
  show(receipt());
  expect(screen.getByText("Veto applied")).toBeInTheDocument();
  expect(screen.getByText(/not a paper fill/)).toBeInTheDocument();
});

test("unfamiliar activity does not become an applied veto or a manipulation label", () => {
  show(receipt({ in_distribution: false, parameters: { applied: false, support_evidence_version: 1, support_reason: "outside_feature_support", support_feature: "trade_density_5m", support_feature_z: 6.3994, support_failed_feature_count: 2, policy_origin_status: "recorded", policy_origin_relation: "later_attempt", policy_origin_episode_id: "policy-first" } }));
  expect(screen.getByText("Not applied · support unavailable")).toBeInTheDocument();
  expect(screen.getByText(/trade density 5m \(6.40 standard deviations\); 2 features failed/)).toBeInTheDocument();
  expect(screen.getByText(/linked to the first Policy opportunity/)).toHaveAttribute("title", "policy-first");
  expect(screen.queryByText("Veto applied")).not.toBeInTheDocument();
});

test.each([
  [{ parameters: {} }, "Application not recorded"],
  [{ in_distribution: false, parameters: { applied: true } }, "Receipt needs review"],
  [{ parameters: { applied: false }, baseline_actionable: false }, "Baseline not actionable"],
  [{ parameters: { applied: false } }, "Not applied to this decision"],
  [{ proposed_action: "support" }, "Entry supported"],
])("old or unapplied receipts remain honest: %s", (patch, expected) => {
  show(receipt(patch as Partial<DecisionSkillReceipt>));
  expect(screen.getByText(expected)).toBeInTheDocument();
});

test("payload failure and unknown legacy support are not attributed to market activity", () => {
  show(receipt({ in_distribution: false, parameters: { applied: false, support_evidence_version: 1, support_reason: "nonlinear_payload_unavailable" } }));
  expect(screen.getByText(/payload was unavailable or failed verification/)).toBeInTheDocument();
  expect(screen.queryByText(/Outside support:/)).not.toBeInTheDocument();
});

test("absent legacy assessments are not reconstructed", () => {
  const { container } = render(<SkillDecisionEvidence />);
  expect(container).toBeEmptyDOMElement();
});

test.each([
  { proposed_action: "future_recipe" },
  { baseline_actionable: false },
  { skill: "sizing", proposed_action: "veto" },
  { in_distribution: undefined },
])("inconsistent or future applied receipts are not reported as success: %s", patch => {
  show(receipt(patch as Partial<DecisionSkillReceipt>));
  expect(screen.getByText("Receipt needs review")).toBeInTheDocument();
  expect(screen.queryByText("Size adjustment applied")).not.toBeInTheDocument();
});

test("a retained first identity does not imply the original proof is retained", () => {
  show(receipt({ parameters: { applied: false, policy_origin_status: "recorded", policy_origin_relation: "later_attempt", policy_origin_episode_id: "policy-" + "f".repeat(64) } }));
  expect(screen.getByText(/linked to the first Policy opportunity/)).toBeInTheDocument();
  expect(screen.queryByText(/proof is preserved/)).not.toBeInTheDocument();
  expect(screen.getByText(/first Policy opportunity/)).not.toHaveTextContent("f".repeat(64));
});

test.each(["0.5", "1.5", "2"])("valid applied sizing remains visible: %s", multiplier => {
  render(<SkillDecisionEvidence assessments={{ sizing: receipt({ skill: "sizing", proposed_action: multiplier }) }} />);
  expect(screen.getByText("Size adjustment applied")).toBeInTheDocument();
});

test("valid Entry support remains visible and neutral sizing is not an applied change", () => {
  render(<SkillDecisionEvidence assessments={{ entry: receipt({ skill: "entry", proposed_action: "support" }), sizing: receipt({ skill: "sizing", proposed_action: "1", parameters: { applied: false } }) }} />);
  expect(screen.getByText("Entry supported")).toBeInTheDocument();
  expect(screen.getByText("Not applied to this decision")).toBeInTheDocument();
  expect(screen.queryByText("Size adjustment applied")).not.toBeInTheDocument();
});

test.each([undefined, 2])("unversioned or future support details stay unknown: %s", version => {
  const parameters: NonNullable<DecisionSkillReceipt["parameters"]> = { applied: false, support_reason: "outside_feature_support", support_feature: "trade_density_5m" };
  if (version !== undefined) parameters.support_evidence_version = version;
  show(receipt({ in_distribution: false, parameters }));
  expect(screen.getByText("Specific support details are unavailable for this receipt.")).toBeInTheDocument();
  expect(screen.queryByText(/Outside support:/)).not.toBeInTheDocument();
});

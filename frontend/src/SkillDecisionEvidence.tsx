import type { DecisionSkillReceipt } from "./types";

const skills = ["entry", "manipulation", "sizing"] as const;
const label = (value: string) => value.replaceAll("_", " ");

function verdict(receipt: DecisionSkillReceipt, skill: typeof skills[number]): string {
  const applied = receipt.parameters?.applied;
  if (receipt.skill !== skill || typeof receipt.in_distribution !== "boolean"
    || typeof receipt.baseline_actionable !== "boolean") return "Receipt needs review";
  if (applied !== true && applied !== false) return "Application not recorded";
  if (applied) {
    if (!receipt.in_distribution || !receipt.baseline_actionable) return "Receipt needs review";
    if (skill === "sizing") return ["0.5", "1.5", "2"].includes(receipt.proposed_action)
      ? "Size adjustment applied" : "Receipt needs review";
    return receipt.proposed_action === "veto" ? "Veto applied"
      : receipt.proposed_action === "support" ? "Entry supported" : "Receipt needs review";
  }
  if (!receipt.in_distribution) return "Not applied · support unavailable";
  return receipt.baseline_actionable ? "Not applied to this decision" : "Baseline not actionable";
}

function supportDetail(receipt: DecisionSkillReceipt): string {
  const p = receipt.parameters ?? {};
  if (receipt.in_distribution) return "Within the saved skill's support range.";
  if (p.support_evidence_version !== 1) return "Specific support details are unavailable for this receipt.";
  if (p.support_reason === "outside_feature_support" && typeof p.support_feature === "string") {
    const z = p.support_feature_z;
    const count = p.support_failed_feature_count;
    return `Outside support: ${label(p.support_feature)}${typeof z === "number" && Number.isFinite(z) ? ` (${z.toFixed(2)} standard deviations)` : ""}${typeof count === "number" && count > 1 ? `; ${count} features failed` : ""}. Unfamiliar does not establish manipulation.`;
  }
  if (p.support_reason === "nonlinear_payload_unavailable") return "The saved model payload was unavailable or failed verification.";
  if (p.support_reason === "invalid_support_parameters") return "The saved model support parameters were invalid.";
  if (p.support_reason === "coach_support_unavailable") return "The Coach policy had no usable support for this input.";
  return "The skill had no supported influence. A specific cause was not recorded.";
}

/** Prediction, applied authority and actual fills are separate evidence. */
export default function SkillDecisionEvidence({ assessments }: { assessments?: Record<string, DecisionSkillReceipt> }) {
  const recorded = skills.filter(skill => assessments?.[skill]);
  if (!recorded.length) return null;
  return <>
    <h3>Skill influence on this decision</h3>
    <div className="evidence-grid">{recorded.map(skill => {
      const receipt = assessments?.[skill];
      if (!receipt) return null;
      const p = receipt.parameters ?? {};
      const effect = verdict(receipt, skill);
      return <div key={skill}>
        <span>{label(skill)}</span><strong>{effect}</strong>
        <small>{effect === "Receipt needs review" ? "Saved fields are inconsistent or unsupported; no applied effect is inferred." : supportDetail(receipt)}</small>
        {typeof p.policy_origin_episode_id === "string" && p.policy_origin_status === "recorded" && <small title={p.policy_origin_episode_id}>
          {p.policy_origin_relation === "original_decision" ? "Original Policy opportunity" : p.policy_origin_relation === "later_attempt" ? "Later attempt; linked to the first Policy opportunity" : "Original Policy link; attempt ordering unconfirmed"}
        </small>}
      </div>;
    })}</div>
    <p>An unapplied proposal adds no skill veto; Baseline and the remaining guards still decide. This receipt is not a paper fill or a verdict that trading activity is legitimate.</p>
  </>;
}

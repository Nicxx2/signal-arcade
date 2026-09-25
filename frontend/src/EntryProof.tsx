import type { ReactNode } from "react";
import { ChevronDown, ShieldCheck } from "lucide-react";
import type { ChallengerSkillStatus, EntryProofIdentity, EntryProofStatus, LearningStatus, ReadinessGate } from "./types";
import { entryProofSummary, supportedEntryProof } from "./entryProofModel";
import LearningFitDetails from "./LearningFitDetails";

const familyName = (family: string | undefined) => family === "linear" ? "Linear" : family === "xgboost" ? "XGBoost" : family === "deterministic" ? "Deterministic" : "Family unknown";
const roles: Record<EntryProofStatus["families"][number]["state"], string> = {
  collecting: "Collecting evidence", proof_not_met: "Proof not met", qualified: "Qualified",
  queued: "Qualified · queued", testing: "In a Champion battle", champion: "Saved Champion",
  active: "Active", suspended: "Suspended", previously_tested: "Previously compared",
};
const identityText = (identity: EntryProofIdentity) => `${identity.codename || "Unnamed artifact"} · ${familyName(identity.model_family)}`;

const coverageLabels = {
  usable: "Usable outcomes (including losses)",
  quote_liquidity: "Quote failed: insufficient real reserves",
  quote_fees: "Quote failed: fees exceed proceeds",
  quote_other: "Other or unspecified quote failures",
  stale_route: "Stale route at checkpoint expiry",
  window_elapsed: "Checkpoint window elapsed",
  other_missing: "Other or unknown missing outcomes",
} as const;

function FittedCoverage({ artifact }: { artifact: NonNullable<ChallengerSkillStatus["latest_candidate"]> }) {
  const coverage = artifact.coverage_breakdown;
  const counts = coverage ? Object.keys(coverageLabels).map(key => coverage[key as keyof typeof coverageLabels]) : [];
  const fraction = artifact.metrics?.outcome_availability;
  const minimum = artifact.minimum_outcome_coverage === undefined ? 0.70 : artifact.minimum_outcome_coverage;
  const requirement = typeof minimum === "number" && Number.isFinite(minimum) ? `${(minimum * 100).toFixed(0)}%` : "unknown";
  const valid = coverage?.schema === 1 && Number.isInteger(coverage.resolved) && coverage.resolved > 0 && coverage.resolved <= 1000
    && counts.every(value => Number.isInteger(value) && value >= 0 && value <= 1000)
    && counts.reduce((sum, value) => sum + value, 0) === coverage.resolved
    && coverage.usable === artifact.sample_count && typeof fraction === "number" && Number.isFinite(fraction)
    && Math.abs(coverage.usable / coverage.resolved - fraction) <= 1e-9;
  if (!valid || !coverage) return <p className="entry-proof-note">Coverage breakdown unavailable for this generation.</p>;
  return <section className="entry-proof-note" aria-label="Fitted cohort coverage">
    <strong>{coverage.usable.toLocaleString()} / {coverage.resolved.toLocaleString()} usable outcomes · {(100 * fraction).toFixed(1)}%</strong>
    <ul>{Object.entries(coverageLabels).map(([key, label]) => <li key={key}>{label}: {coverage[key as keyof typeof coverageLabels].toLocaleString()}</li>)}</ul>
    <p>Recorded for this generation’s fitted Discovery cohort. Policy proof is assessed separately. Quote failures remain valid missing outcomes; missed checkpoints are not guaranteed recoverable. The requirement for this generation is {requirement}.</p>
  </section>;
}

export default function EntryProof({ learning, renderGates }: { learning: LearningStatus; renderGates: (gates: ReadinessGate[]) => ReactNode }) {
  const proof = supportedEntryProof(learning);
  if (!proof) return <div className="entry-proof-panel">
    <p className="entry-proof-note">Family-specific proof is unavailable from this server response. The legacy diagnostics below belong to Linear and include shared activation checks; they are not the XGBoost candidate’s checklist. The skill cards show each displayed candidate’s own proof.</p>
    <details className="entry-family-proof"><summary><strong>Legacy Linear diagnostics</strong><ChevronDown size={15} /></summary>
      <p className="entry-proof-note">{learning.latest_model ? `Linear model: ${learning.latest_model.version}` : "No Linear model recorded yet."}</p>
      {renderGates(learning.qualification_gates ?? [])}
    </details>
    <p className="entry-proof-note">Activation readiness: {entryProofSummary(learning)}. The engine controls eligibility; displayed check counts grant no permission.</p>
  </div>;

  const activation = proof.activation;
  return <div className="entry-proof-panel">
    <p className="entry-influence-note"><ShieldCheck size={14} /><span><strong>One Entry crown. Two model families.</strong> Linear or XGBoost can earn the first crown through independent proof. Later contenders must prove an advantage against the saved Champion. Trading influence requires separate activation checks and consent. These checks apply only to Entry; other skills have their own activation proof.</span></p>
    <div className="entry-family-grid">
      {(["linear", "xgboost"] as const).map(family => {
        const report = proof.families.find(item => item.family === family);
        // Never label mismatched payloads as another family's evidence.
        const artifact = report?.artifact?.model_family === family ? report.artifact : null;
        const gates = artifact ? report?.gates ?? [] : [];
        const passed = gates.filter(g => g.state === "passed").length;
        const time = artifact ? Date.parse(artifact.created_at) : Number.NaN;
        return <details className="entry-family-proof" key={family}>
          <summary><span><strong>{familyName(family)} proof</strong><small>{artifact?.codename || (artifact ? "Unnamed artifact" : "No fitted artifact yet")}</small></span><span className="entry-family-meta"><b>{artifact ? roles[report!.state] ?? "Status unavailable" : "Collecting evidence"}</b><small>{gates.length ? `${passed} / ${gates.length} checks passing` : "Waiting for family proof"}</small><ChevronDown size={15} /></span></summary>
          <div className="entry-family-body">
            <p className="entry-proof-note">{family === "linear" ? "Latest Linear generation in this risk and configuration context." : "Latest nonlinear generation. XGBoost must also justify its complexity against the Linear model fitted on the same evidence."}</p>
            {artifact && <><p className="entry-proof-identity">{artifact.version}</p><p className="entry-proof-note">{Number.isFinite(time) ? new Date(time).toLocaleString() : "Recorded time unavailable"}</p><LearningFitDetails artifact={artifact} /></>}
            {artifact && <FittedCoverage artifact={artifact} />}
            {renderGates(gates)}
          </div>
        </details>;
      })}
    </div>
    <p className="entry-proof-note">Each checklist belongs to its named generation. Coverage measures usable outcomes, not prediction accuracy or win rate. Current collection coverage can differ from a fitted generation's coverage; meeting the recorded coverage requirement still leaves its other proof checks to pass. Family requirements differ, so check totals are not a race percentage. The skill card identifies any battle currently underway.</p>
    <section className="entry-activation" aria-label="Entry activation readiness">
      <header><span><strong>Entry activation readiness</strong><small>{entryProofSummary(learning)}</small></span><ShieldCheck size={18} /></header>
      <p>{activation.champion ? <>Saved Champion: <strong>{identityText(activation.champion)}</strong></> : "No Entry Champion has been recorded for this context yet."}</p>
      {activation.subject && <p>{activation.source === "legacy_linear" ? "Legacy activation candidate" : "Activation checks apply to"}: <strong title={activation.subject.version}>{identityText(activation.subject)}</strong></p>}
      {learning.mode === "active" && learning.collecting_from_current_source && activation.active && <p>Influencing entries: <strong title={activation.active.version}>{identityText(activation.active)}</strong></p>}
      {!learning.collecting_from_current_source && <p className="entry-proof-note">This source is separate from live-paper learning. Saved proof grants no influence here.</p>}
      {learning.mode === "off" && <p className="entry-proof-note">Learning is paused. Saved qualification is separate from the current mode.</p>}
      <p className="entry-proof-note">{typeof learning.auto_participation === "boolean" ? learning.auto_participation ? "Automatic support is allowed. Entry joins only when learning is running and its current activation checks pass." : "Automatic support is off. A saved crown does not enable trading influence." : activation.consent_granted ? "Consent was previously granted. The current mode and engine approval still control influence." : "Consent has not been granted. A crown alone does not switch learning to Active."}</p>
      {renderGates(activation.gates)}
      <p className="entry-proof-note">Entry may select or reject Baseline-approved opportunities. Manipulation, Sizing and Exit join only after their own independent and combined proof.</p>
    </section>
  </div>;
}

import { ChevronDown, ShieldCheck } from "lucide-react";
import type { SeasonStrategyUsage } from "./types";

const skillNames = { entry: "Entry", manipulation: "Manipulation", sizing: "Sizing", exit: "Exit" };
function recordedTime(value: string | null | undefined) {
  const time = value ? new Date(value) : null;
  return time && Number.isFinite(time.getTime()) ? time.toLocaleString() : "Time not recorded";
}

export default function SeasonStrategy({ usage }: { usage?: SeasonStrategyUsage }) {
  const status = usage?.status ?? "unknown";
  const skills = (usage?.skills_observed ?? []).map(skill => skillNames[skill]).filter(Boolean);
  const assisted = status === "assisted" || status === "mixed";
  const hasChampions = usage?.champion_observed ?? usage?.participants.some(p => p.kind === "champion") ?? false;
  const support = hasChampions ? "Champion support" : skills.length ? "Learner support" : "AI critic support";
  const label = status === "baseline" ? "Baseline only"
    : status === "no_decisions" ? "No decisions recorded"
      : assisted ? `${status === "mixed" ? "Mixed · " : ""}${support}` : "Influence not recorded";
  const partial = Boolean(usage?.tracking_started_at && !usage.complete_from_start);
  return <details className={`season-strategy state-${status}`}>
    <summary><ShieldCheck size={13} /><span>Strategy used</span><strong>{label}</strong>
      {assisted && skills.length > 0 && <small>{skills.join(" + ")}{usage?.ai_observed ? " + AI critic" : ""}</small>}
      {(partial || usage?.unattributed_use) && <em>Partial history</em>}<ChevronDown size={13} className="season-strategy-chevron" />
    </summary>
    <div className="season-strategy-content">
      <p>{status === "unknown" ? "The full season's influence was not recorded. Current learning settings cannot establish what happened earlier."
        : status === "no_decisions" ? "Tracking is ready. Strategy use appears after a paper decision is recorded."
          : status === "baseline" ? "Only Baseline decisions have been recorded in this season. Shadow learning and saved champions do not count as influence."
            : status === "mixed" ? "Both Baseline-only and assisted decisions were recorded. This does not imply that champion support was active throughout the season."
              : "Assisted decisions were recorded. These labels describe participation, not proof that a participant improved the result."}</p>
      {partial && <p>Tracking began {recordedTime(usage?.tracking_started_at)}. Earlier participation is unknown.</p>}
      {usage?.unattributed_use && <p>Some recorded use had incomplete participant details. The confirmed participants below do not describe the whole season.</p>}
      {usage?.first_baseline_at && <p>First recorded Baseline-only decision: {recordedTime(usage.first_baseline_at)}.</p>}
      {Boolean(usage?.participants.length) && <ul>{usage!.participants.map(p => <li key={`${p.kind}:${p.skill}:${p.version}`}>
        <strong>{p.name}{p.skill ? ` · ${skillNames[p.skill]}` : ""}</strong>
        <span>First recorded use {recordedTime(p.first_used_at)}</span>
        <code>{p.version}</code>
      </li>)}</ul>}
      {assisted && <p>Recorded use can include an entry approval or veto, a size adjustment, or a learned exit review. First use is not an activation or suspension timestamp.</p>}
      {usage?.details_limited && <p>Version details are limited to the first 128 participants. The skill summary continues to include later use.</p>}
    </div>
  </details>;
}

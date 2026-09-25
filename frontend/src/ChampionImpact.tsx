import { useState } from "react";
import { CircleHelp, ShieldCheck } from "lucide-react";
import { ChampionRecordPortrait } from "./championArena/FighterPortrait";
import type { ChampionImpactComparison, LearningStatus } from "./types";

type Skill = "entry" | "manipulation" | "sizing" | "exit";
type Subject = Skill | "team";
const SKILLS: Skill[] = ["entry", "manipulation", "sizing", "exit"];
const LABELS: Record<Subject, string> = { team: "Team", entry: "Entry", manipulation: "Manipulation", sizing: "Sizing", exit: "Exit" };
const STATES = { collecting: "Collecting comparisons", positive: "Observed advantage", negative: "Observed disadvantage", uncertain: "No clear advantage" };
type Props = {
  learning: Pick<LearningStatus, "mode" | "collecting_from_current_source" | "active_skill_versions" | "champion_impact" | "champion_records" | "skills">;
  seasonId: string | null;
  profile: string | null;
  serverTime: string;
};

const finite = (value: number | null | undefined): value is number => typeof value === "number" && Number.isFinite(value);
const percent = (value: number | null) => finite(value) ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%` : "—";
const points = (value: number | null) => finite(value) ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)} pp` : "—";
const date = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : "Not recorded";
const sameVersions = (left: Partial<Record<Skill, string>>, right: Partial<Record<Skill, string>>) =>
  Object.keys(left).length === Object.keys(right).length && Object.entries(left).every(([key, value]) => right[key as Skill] === value);

function validComparison(value: ChampionImpactComparison): boolean {
  return Object.hasOwn(STATES, value.state) && [value.observed_count, value.usable_count, value.pending_count, value.not_reached_count].every(x => Number.isInteger(x) && x >= 0)
    && value.usable_count <= value.observed_count && value.observed_count <= 60
    && finite(value.coverage) && value.coverage >= 0 && value.coverage <= 1
    && [value.mean_advantage, value.reference_mean, value.supported_mean, value.lower_bound, value.upper_bound].every(x => x === null || finite(x * 100));
}

/** A passive view of frozen, paired evidence. Never a control or qualification signal. */
export function ChampionImpact({ learning, seasonId, profile, serverTime }: Props) {
  const versions = learning.active_skill_versions ?? {};
  const active = SKILLS.filter(skill => Boolean(versions[skill]));
  const [selection, setSelection] = useState<Subject>(() => active.length > 1 ? "team" : active[0] ?? "entry");
  const subject = selection === "team" && active.length < 2 ? active[0] ?? "entry" : selection;
  const report = learning.champion_impact;
  const paused = learning.mode === "off" || !learning.collecting_from_current_source;
  const selectedStatus = learning.skills?.find(skill => skill.skill === subject);
  const suspended = selectedStatus?.state === "suspended";
  const enabled = learning.mode === "active" && (subject === "team" ? active.length > 1 : Boolean(versions[subject]) && !suspended);
  const age = report ? Date.parse(serverTime) - Date.parse(report.as_of) : NaN;
  const current = report?.schema_version === 1 && report.state === "available" && Boolean(seasonId) && Boolean(profile)
    && !learning.skills?.some(skill => Boolean(versions[skill.skill]) && skill.state === "suspended")
    && report.season_id === seasonId && report.profile_fingerprint === profile && sameVersions(report.versions, versions)
    && Number.isFinite(age) && age >= -5000 && age <= 120000;
  const candidate = current ? report.comparisons.find(item => item.subject === subject) : undefined;
  const comparison = !paused && enabled && candidate && validComparison(candidate) ? candidate : undefined;
  const counts = comparison?.actions;
  const actions = counts && Object.values(counts).every(x => Number.isInteger(x) && x >= 0)
    && Object.values(counts).reduce((a, b) => a + b, 0) === comparison.observed_count ? counts : undefined;
  const sample = comparison && report?.execution_sample?.state === "available" ? report.execution_sample : undefined;
  const entrySample = sample?.skills?.find(item => item.skill === subject);
  const entries = entrySample && [entrySample.observed_count, entrySample.supported_entry, entrySample.fallback, entrySample.unknown, entrySample.later_fallback].every(x => Number.isInteger(x) && x >= 0 && x <= 30)
    && entrySample.supported_entry + entrySample.fallback + entrySample.unknown === entrySample.observed_count
    && entrySample.later_fallback <= entrySample.fallback ? entrySample : undefined;
  const state = comparison?.state ?? "collecting";
  const participants = subject === "team" ? active : [subject];
  const message = paused ? "Comparison paused" : suspended ? "Support suspended" : !enabled ? "Waiting for active support" : "Waiting for current comparisons";
  const detail = paused ? "Fresh comparisons resume when learning and support are running on this source."
    : suspended ? "Baseline retains this role. New candidates and recovery follow their normal proof rules."
      : !enabled ? "This skill needs an active Champion before its support can be compared. Learning and qualification continue."
        : "Results appear after matching evidence is recorded for this season and current Champions.";
  const hasRange = comparison && finite(comparison.lower_bound) && finite(comparison.upper_bound) && finite(comparison.mean_advantage);
  const extent = hasRange ? Math.max(0.01, Math.abs(comparison.lower_bound!), Math.abs(comparison.upper_bound!), Math.abs(comparison.mean_advantage!)) * 1.15 : 0.01;
  const position = (value: number) => 50 + value / extent * 50;

  return <section className="champion-impact" aria-label="Champion impact">
    <header><div><span className="eyebrow">CHAMPION IMPACT</span><h3>What does support change?</h3><p>Modeled outcomes · same opportunities</p></div><ShieldCheck size={22} aria-hidden="true" /></header>
    <div className="impact-select" role="group" aria-label="Choose comparison">
      {(active.length > 1 ? ["team" as const, ...SKILLS] : SKILLS).map(skill => <button type="button" key={skill} aria-pressed={subject === skill} onClick={() => setSelection(skill)}>{LABELS[skill]}</button>)}
    </div>
    <div className="impact-contenders">
      {participants.map(skill => {
        const record = learning.champion_records?.find(item => item.skill === skill && item.champion_version === versions[skill]);
        return record ? <span className="impact-champion" key={skill}><ChampionRecordPortrait record={record} /><span><strong>{record.champion_codename}</strong><small>{LABELS[skill]}{record.champion_generation !== null ? ` · v${record.champion_generation}` : ""}</small></span></span> : null;
      })}
    </div>
    {comparison ? <>
      <div className={`impact-verdict tone-${state}`}><span />{STATES[state]}</div>
      <dl className="impact-values">
        <div><dt>{subject === "exit" ? "Same size, normal review" : subject === "team" ? "Baseline reference" : "Without this skill"}</dt><dd>{percent(comparison.reference_mean)}</dd></div>
        <div><dt>With support</dt><dd>{percent(comparison.supported_mean)}</dd></div>
        <div><dt>Mean difference</dt><dd>{points(comparison.mean_advantage)}</dd></div>
      </dl>
      {hasRange && <div className={`impact-scale tone-${state}`} role="img" aria-label={`Approximate uncertainty range ${points(comparison.lower_bound)} to ${points(comparison.upper_bound)}`}>
        <div className="impact-track"><i className="impact-zero" /><span className="impact-range" style={{ left: `${position(comparison.lower_bound!)}%`, width: `${Math.max(0.6, position(comparison.upper_bound!) - position(comparison.lower_bound!))}%` }} /><b style={{ left: `${position(comparison.mean_advantage!)}%` }} /></div>
        <div className="impact-scale-labels"><span>Lower outcome</span><span>Equal</span><span>Higher outcome</span></div>
      </div>}
      <p className="impact-sample">{comparison.usable_count} usable / {comparison.observed_count} resolved · {(comparison.coverage * 100).toFixed(1)}% coverage{comparison.pending_count > 0 ? ` · ${comparison.pending_count} pending` : ""}</p>
      {actions && <p className="impact-sample">Original opportunities: {actions.supported_entry} supported entries · {actions.supported_veto} supported vetoes · {actions.fallback} Baseline fallbacks · {actions.unavailable} unknown receipts.</p>}
      {actions && actions.supported_veto > 0 && actions.supported_entry === 0 && <p>No supported entries in this window. Avoiding trades can preserve cash; this alone does not demonstrate selective entry.</p>}
      {actions && comparison.cash_reference_mean === 0 && <p>Keeping cash on the same quoted opportunities returns 0%. This reference does not simulate a portfolio or qualify a skill.</p>}
      {entries && <details className="impact-entries"><summary>Recent actual entries · bounded fill sample</summary>
        <p>{entries.supported_entry} supported · {entries.fallback} Baseline fallbacks · {entries.unknown} unknown receipts. {entries.later_fallback} fallbacks linked to a later attempt.</p>
        {entries.outcomes.filter(item => ["fallback", "supported_entry"].includes(item.category) && ["SOL", "USDC"].includes(item.currency)
          && Number.isInteger(item.decimals) && item.decimals >= 0 && item.decimals <= 9
          && [item.closed_count, item.unresolved_count, item.winning_count].every(x => Number.isInteger(x) && x >= 0 && x <= 30)
          && item.winning_count <= item.closed_count && Number.isSafeInteger(item.net_minor)).map(item => <p key={`${item.category}-${item.currency}`}>
          {item.category === "fallback" ? "Fallback" : "Supported"}: {item.closed_count} matched closed trades · {item.winning_count} positive · {item.closed_count ? `${(item.net_minor / 10 ** item.decimals).toFixed(4)} ${item.currency} after costs` : "Result pending"} · {item.unresolved_count} open or unmatched.
        </p>)}
        <p>At most 30 recent fills and their exact entry records. Older or missing records limit this sample; {sample?.unlinked_entries ?? 0} entries could not be linked. A later-attempt link does not prove an earlier veto. These actual results are separate from Policy proof and do not establish legitimacy or future profit.</p>
      </details>}
      {comparison && report?.execution_sample?.state === "unavailable" && <p>Actual-entry reporting is unavailable; no empty or healthy sample is inferred.</p>}
    </> : <div className="impact-empty"><strong>{message}</strong><p>{detail}</p></div>}
    <footer><span>Checkpoint comparison, not portfolio profit.</span><details className="impact-help"><summary aria-label="How Champion impact is measured"><CircleHelp size={18} /><span>How this works</span></summary>
      <div>
        <p>Pairs use the same Baseline-approved opportunity and recorded, fee-inclusive outcomes. Entry and Manipulation compare taking the opportunity with preserving cash when vetoed. Sizing compares its bounded size with 1×. These individual comparisons use the 5-minute checkpoint.</p>
        <p>Exit compares its frozen review time with the normal review, keeping the same size. Team applies the active skills together against a 1× Baseline reference at the normal review. Vetoes count once; later roles are not reached. Individual differences must not be added together.</p>
        <p>This describes saved checkpoint decisions, including modeled Exit timing. It does not replay adaptive position management, freed cash, later trades or a second portfolio. Both outcomes can lose money even when the difference is positive. See Results for actual paper-account performance.</p>
        <p>The view uses up to 60 recently resolved, independent opportunities from the retained Policy evidence, for this season, profile and exact active Champion versions since their latest activation. Missing pairs remain in coverage; pending outcomes are separate. Version, season or activation changes start a new comparison.</p>
        <p>At least 30 usable pairs and 70% coverage are needed for an observed-advantage label. The range is an approximate 95% interval around the paired mean; it does not prove future performance or account for every market dependency. This display never changes permission, qualification or trading.</p>
        {comparison && <p>Window: {date(comparison.from)} – {date(comparison.to)}. Reference checkpoint: {comparison.reference_horizon_seconds / 60} minutes. {comparison.not_reached_count} opportunities did not reach this role after an earlier veto. Updated {date(report?.as_of ?? null)}.</p>}
      </div>
    </details></footer>
  </section>;
}

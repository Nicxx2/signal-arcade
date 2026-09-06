import type { CSSProperties } from "react";
import { Crown, ShieldCheck } from "lucide-react";
import type { ArenaView } from "./model";
import { percentage, recordedDate } from "./model";

import { SCALE, position, numeric, edgeText, battleReadout, nextCheckText } from "./readout";

function Progress({ value, maximum, label }: { value: number; maximum: number; label: string }) {
  return <div className="ca-progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={maximum} aria-valuenow={Math.min(value, maximum)} aria-valuetext={`${value} of ${maximum}; evidence progress only`}><span style={{ width: `${Math.min(1, Math.max(0, value / maximum)) * 100}%` }} /></div>;
}

export default function ArenaReadout({ view, stale }: { view: ArenaView; stale: boolean }) {
  const checkpoint = view.replayFinal === false;
  const historical = view.mode === "recap" && !checkpoint;
  const first = historical && view.outcome === "first_champion";
  const training = view.mode === "training";
  const battle = historical ? !first : checkpoint || view.mode === "battle" || view.mode === "interrupted";
  const colors = { "--champion-color": view.left?.color ?? "#a3b8cc", "--contender-color": view.right?.color ?? "#a3b8cc" } as CSSProperties;

  if (first || training || view.mode === "champion") {
    const passed = view.gates.filter(gate => gate.state === "passed").length;
    const total = view.gates.length;
    const next = view.gates.find(gate => gate.state !== "passed");
    const paused = !historical && view.paused;
    const title = first ? "First Champion crowned" : training ? view.superseded ? "Saved candidate proof" : paused ? "Proof updates paused" : "Road to the first Champion" : view.superseded ? "Saved Champion" : "Current saved Champion";
    return <section className="ca-readout" aria-label="Champion progress" style={colors}>
      <div className="ca-readout-heading">{training ? <ShieldCheck size={19} /> : <Crown size={19} />}<div><span>{historical ? "SAVED MILESTONE" : "INDEPENDENT SKILL PROOF"}</span><h3>{title}</h3></div></div>
      <p>{view.superseded ? "This profile belongs to an earlier model version. Its saved status is separate from the current generation." : first ? `${view.left?.name ?? "The recorded Champion"} earned the first crown through independent skill proof. No opponent was needed.` : training ? `${view.left?.name ?? "This contender"} must pass each required check. Progress can move backward as evidence changes.` : `${view.left?.name ?? "This Champion"} holds the saved crown. Permission to influence trading is separately gated.`}</p>
      {first && !view.left && <p>Champion identity unavailable</p>}
      {training && (!paused || view.superseded) && total > 0 && <div className="ca-proof-progress"><div><strong>{passed} / {total} checks passing</strong><span>{view.superseded ? "Saved evidence" : stale ? "Last received evidence" : "Current evidence"}</span></div><Progress value={passed} maximum={total} label="Independent checks passing" /><p>{next ? <>{view.superseded ? "Unmet check" : "Next check"}: <strong>{next.label}</strong>. {nextCheckText(next)}</> : "The displayed checks pass. A recorded qualification result is still required; a crown is not guaranteed."}</p></div>}
      {training && ((paused && !view.superseded) || total === 0) && <p className="ca-readout-note">{paused && !view.superseded ? "Waiting for fresh learning evidence before showing current progress." : "Qualification checks are not available yet."}</p>}
      {!training && <p className="ca-readout-note">{first ? `${recordedDate(view.event?.occurred_at)} · ` : ""}Saved status and permission to influence trading are separate.</p>}
    </section>;
  }
  if (!battle) return null;
  const readout = battleReadout(view, stale);
  const countReady = !historical && (checkpoint || (!view.paused && view.mode === "battle")) && numeric(view.usable) && numeric(view.observed) && Number.isInteger(view.usable) && Number.isInteger(view.observed) && view.usable >= 0 && view.usable <= view.observed && numeric(view.minimum) && view.minimum > 0;
  const point = readout.plot ? position(view.mean!) : null;
  const range = readout.band ? [position(view.lower!), position(view.upper!)] : null;
  const plotLabel = point === null ? "Advantage unavailable; waiting for valid evidence" : `${readout.delayed ? "Last received evidence. " : ""}${readout.preliminary ? "Preliminary evidence. " : ""}Contender average advantage ${edgeText(view.mean)}${range ? `; uncertainty range ${edgeText(view.lower)} to ${edgeText(view.upper)}` : "; historical uncertainty range unavailable"}. Display scale minus 5 to plus 5 percentage points${Math.abs(view.mean!) > SCALE ? "; average extends beyond the displayed scale" : ""}. This is not a win probability.`;
  return <section className="ca-readout" aria-label="Battle explanation" style={colors}>
    <div className="ca-readout-heading">{historical && view.outcome !== "inconclusive" ? <Crown size={19} /> : <ShieldCheck size={19} />}<div><span>{historical ? "RECORDED RESULT" : checkpoint ? "RECORDED CHECKPOINT" : readout.delayed ? "LAST RECEIVED EVIDENCE" : "LIVE EVIDENCE"}</span><h3 aria-live={checkpoint ? "off" : "polite"} aria-atomic="true">{readout.title}</h3></div></div>
    <p>{readout.detail}</p>
    {readout.exactLevel && <p className="ca-readout-note">0.0 pp means the same measured average on these shared outcomes. It does not mean zero trading profit or missing data. Different generations can reach the same result.</p>}
    {historical && ((view.outcome === "promoted" && !view.right) || (view.outcome === "defended" && !view.left)) && <p>Champion identity unavailable</p>}
    {historical && <p className="ca-balance-caption">{view.usable ?? "Unknown"} usable shared outcomes · {percentage(view.coverage)} coverage</p>}
    <div className={`ca-balance ${point === null ? "is-waiting" : readout.preliminary ? "is-preliminary" : ""}`} role="img" aria-label={plotLabel}>
      <div className="ca-balance-labels" aria-hidden="true"><span>Champion advantage</span><span>Contender advantage</span></div>
      <div className="ca-balance-track" aria-hidden="true"><i className="ca-balance-zero" />{point !== null && <><i className="ca-balance-fill" style={{ left: `${Math.min(50, point)}%`, width: `${Math.abs(point - 50)}%`, background: point < 50 ? "var(--champion-color)" : "var(--contender-color)" }} />{range && <i className="ca-balance-range" style={{ left: `${range[0]}%`, width: `${range[1]! - range[0]!}%` }} />}<i className="ca-balance-marker" style={{ left: `${point}%` }} /></>}</div>
      <div className="ca-balance-scale" aria-hidden="true"><span>−5 pp</span><span>Level</span><span>+5 pp</span></div>
    </div>
    <p className="ca-balance-caption">{point === null ? historical ? "The saved comparison does not include enough information to position the marker." : "The marker appears when a valid measured average and uncertainty range are available." : <>{readout.preliminary ? "Preliminary average" : "Average edge"}: <strong>{edgeText(view.mean)}</strong>. {Math.abs(view.mean!) > SCALE && "Beyond the displayed ±5 pp scale. "}{range ? view.lower === view.upper ? "The recorded uncertainty range is a single point." : "The band shows uncertainty." : `Conservative estimate: ${edgeText(view.lower)}.`}{readout.preliminary && " Every qualification guard still applies."}</>}</p>
    {countReady && <div className="ca-proof-progress"><div><strong>{view.usable} / {view.minimum} minimum shared outcomes</strong><span>{view.usable! >= view.minimum ? "Sample minimum reached" : `${view.minimum - view.usable!} more needed`}</span></div><Progress value={view.usable!} maximum={view.minimum} label="Shared outcome evidence" /><p>{numeric(view.coverage) ? `Usable coverage: ${percentage(view.coverage)} · required ${percentage(view.minimumCoverage)}. ` : "Usable coverage is unknown. "}Sample size, coverage and a safe advantage must all pass.</p></div>}
    <p className="ca-readout-note">{checkpoint ? "This checkpoint is past evidence, not a settled result. " : historical ? `${recordedDate(view.event?.occurred_at)} · The animation illustrates this saved result. ` : ""}Bars show evidence and measured advantage, never the probability of a win.</p>
  </section>;
}

import { ChevronDown, GraduationCap, Save } from "lucide-react";
import { useState } from "react";
import { api } from "./api";
import type { CoverageSettings } from "./types";
import type { IssueScope } from "./systemStatus";

type Props = {
  policy: CoverageSettings | undefined;
  refresh: () => Promise<void>;
  busy: boolean;
  setBusy: (value: boolean) => void;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
};

export function LearningCoverageSettings({ policy, refresh, busy, setBusy, reportIssue, resolveIssue }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [confirmed, setConfirmed] = useState<CoverageSettings | null>(null);
  const [draft, setDraft] = useState<{ percent: CoverageSettings["percent"]; revision: number } | null>(null);
  const current = confirmed && (!policy || confirmed.revision > policy.revision) ? confirmed : policy;
  const selected = draft?.percent ?? current?.percent ?? 70;
  // Capabilities come from the server, even while a confirmed save outranks a stale snapshot.
  const advertised = policy ? policy.options : confirmed?.options;
  const options = ([70, 65, 60, 55] as const).filter(percent => Array.isArray(advertised) && advertised.includes(percent));
  const supported = options.some(percent => percent === selected);
  const conflict = !!draft && draft.revision !== current?.revision;
  const changed = selected !== current?.percent || !!current?.error;
  const save = async () => {
    if (!current || busy || conflict || !changed || !supported) return;
    setBusy(true);
    let saved = false;
    try {
      const result = await api.setCoverage(selected, draft?.revision ?? current.revision);
      setConfirmed(result);
      setDraft(null);
      saved = true;
      resolveIssue("learning");
      await refresh();
    } catch (cause) {
      reportIssue("learning", saved ? "Coverage saved; dashboard refresh failed" : "Coverage was not confirmed saved; refresh before retrying", cause);
    } finally {
      setBusy(false);
    }
  };
  return <article className="card settings-card learning-coverage-settings" aria-label="Learning requirements">
    <div className="ai-lab-heading settings-disclosure-head">
      <div className="section-header"><div><h2>Learning requirements</h2><p>Evidence needed for Champion support</p></div></div>
      <div className="settings-disclosure-actions">
        <span className="settings-section-summary"><GraduationCap size={14} /><span><strong>{current ? `${current.percent}% coverage` : "Unavailable"}</strong><small>Saved requirement</small></span></span>
        <button className="button ghost settings-section-toggle" type="button" aria-expanded={expanded} aria-controls="learning-coverage-settings" onClick={() => setExpanded(!expanded)}>{expanded ? "Hide" : "Show"}<ChevronDown size={15} /></button>
      </div>
    </div>
    {expanded && <div className="settings-disclosure-body" id="learning-coverage-settings">
      <div className="provider-fields"><label><span>Skill outcome coverage</span><select aria-describedby="learning-coverage-help" value={selected} disabled={busy || !current || options.length === 0} onChange={event => {
        const percent = options.find(option => option === Number(event.target.value));
        if (current && percent !== undefined) setDraft({ percent, revision: current.revision });
      }}>{!supported && <option value={selected} disabled>{selected}% (unavailable)</option>}{options.map(percent => <option key={percent} value={percent}>{percent}%{percent === 70 ? " (default)" : ""}</option>)}</select></label></div>
      <p className="provider-note" id="learning-coverage-help">Minimum share of usable outcomes for Entry, Manipulation, Sizing and Exit. A lower value accepts less complete evidence, including for ongoing health checks. All other proof and permission checks still apply.</p>
      <p className="provider-note">New generations need fresh validation. Existing proof keeps its recorded requirement; lowering this setting does not revive failed candidates or recovery trials. Raising it can pause Champion support until stricter proof is met.</p>
      <p className="provider-note">Coach research, Coach-derived support and battles involving Coach retain 70%. The separate Champion-impact display also retains its own 70% reporting requirement.</p>
      {current?.error && <p role="alert" className="provider-warning">{current.error}</p>}
      {!current && <p role="status">Coverage settings are unavailable. Refresh after the app has updated.</p>}
      {current && !supported && <p role="status">This choice is unavailable on the current server. Refresh or choose a supported requirement.</p>}
      {conflict && <p role="alert">This setting changed elsewhere. <button className="button ghost" type="button" onClick={() => setDraft(null)}>Use current setting</button></p>}
      <button className="button primary" type="button" disabled={busy || !current || !changed || conflict || !supported} onClick={() => void save()}><Save size={15} />{busy ? "Saving…" : "Save requirement"}</button>
    </div>}
  </article>;
}

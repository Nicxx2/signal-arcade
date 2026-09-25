import { Check, Save } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { IssueScope } from "./systemStatus";
import type { StorageStatus } from "./types";

type Policy = Pick<StorageStatus, "max_database_bytes" | "raw_trade_retention_hours" | "policy_revision">;
type Draft = { maxGb: string; retention: string; revision: number };
type Props = {
  policy: Policy; refresh: () => Promise<void>; busy: boolean; setBusy: (value: boolean) => void;
  reportIssue: (scope: IssueScope, title: string, cause: unknown) => void;
  resolveIssue: (scope: IssueScope) => void;
};
const validRevision = (value: number | undefined): value is number => Number.isSafeInteger(value) && value! >= 0;
const samePolicy = (a: Policy, b: Policy) => a.max_database_bytes === b.max_database_bytes && a.raw_trade_retention_hours === b.raw_trade_retention_hours;

export function StorageSettingsForm({ policy, refresh, busy, setBusy, reportIssue, resolveIssue }: Props) {
  const [confirmed, setConfirmed] = useState<Policy | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<"saved" | "uncertain" | "conflict" | null>(null);
  const inFlight = useRef(false);
  // A save response outranks an older snapshot, without modifying measured storage data.
  const current = confirmed && validRevision(confirmed.policy_revision) && validRevision(policy.policy_revision)
    && confirmed.policy_revision > policy.policy_revision ? confirmed : policy;
  const supported = validRevision(current.policy_revision);
  const conflict = !!draft && draft.revision !== current.policy_revision;
  const maxGb = draft?.maxGb ?? String(current.max_database_bytes / 1024**3);
  const retention = draft?.retention ?? String(current.raw_trade_retention_hours);
  const changed = Math.trunc(Number(maxGb) * 1024**3) !== current.max_database_bytes || Number(retention) !== current.raw_trade_retention_hours;
  const saved = message === "saved" && !!confirmed && confirmed.policy_revision === current.policy_revision && samePolicy(confirmed, current);
  const edit = (field: "maxGb" | "retention", value: string) => {
    if (!supported) return;
    setDraft({ maxGb, retention, revision: draft?.revision ?? current.policy_revision!, [field]: value });
    setMessage(previous => previous === "saved" ? null : previous);
  };
  const refreshAfterSave = () => {
    void refresh().catch(cause => reportIssue("storage", "Storage settings saved; dashboard refresh failed", cause));
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (inFlight.current || busy || !supported || conflict || !changed || message === "uncertain" || message === "conflict") return;
    const limit = Number(maxGb), hours = Number(retention);
    if (!Number.isFinite(limit) || limit < 0.5 || limit > 100 || !Number.isInteger(hours) || hours < 1 || hours > 720) {
      reportIssue("storage", "Storage settings are invalid", new Error("Use 0.5–100 GB and 1–720 retention hours."));
      return;
    }
    inFlight.current = true;
    setSaving(true); setBusy(true); setMessage(null);
    try {
      const result = await api.updateStorageSettings(limit, hours, draft?.revision ?? current.policy_revision!);
      if (!validRevision(result.policy_revision) || result.policy_revision <= current.policy_revision!
        || result.max_database_bytes !== Math.trunc(limit * 1024**3) || result.raw_trade_retention_hours !== hours) {
        throw new Error("The server did not confirm the requested storage policy. Refresh before retrying.");
      }
      setConfirmed(result); setDraft(null); setMessage("saved");
      resolveIssue("storage"); refreshAfterSave();
    } catch (cause) {
      const rejected = cause instanceof ApiError && [400, 401, 403, 409, 422].includes(cause.status);
      setMessage(cause instanceof ApiError && cause.status === 409 ? "conflict" : rejected ? null : "uncertain");
      reportIssue("storage", rejected ? "Storage settings were not saved" : "Storage save could not be confirmed; refresh before retrying", cause);
    } finally {
      inFlight.current = false; setSaving(false); setBusy(false);
    }
  };
  return <>
    <form className="storage-form" onSubmit={save}>
      <label>Live-data budget<input type="number" min="0.5" max="100" step="any" value={maxGb} onChange={event => edit("maxGb", event.target.value)} disabled={saving || busy || !supported} /><span>GB</span></label>
      <label>Raw event history<input type="number" min="1" max="720" step="1" value={retention} onChange={event => edit("retention", event.target.value)} disabled={saving || busy || !supported} /><span>hours</span></label>
      <button className={`button${saved ? " saved" : ""}`} type="submit" disabled={saving || busy || !supported || conflict || !changed || message === "uncertain" || message === "conflict"} aria-live="polite">{saving ? <span className="mini-loader" /> : saved ? <Check size={15} /> : <Save size={15} />}{saving ? "Saving…" : saved ? "Saved" : "Save"}</button>
    </form>
    {!supported && <p className="storage-note" role="status">Protected storage settings are unavailable. Refresh after the server has updated.</p>}
    {(conflict || message === "conflict") && <p className="provider-warning" role="alert">Storage settings changed or could not be saved. Review the current settings before saving.</p>}
    {message === "uncertain" && <p className="provider-warning" role="status">The save may have completed. Refresh and review the current settings before retrying.</p>}
    {(conflict || message === "uncertain" || message === "conflict") && <p className="storage-note"><button className="button ghost" type="button" disabled={busy || saving} onClick={() => { void refresh().catch(cause => reportIssue("storage", "Storage settings refresh failed", cause)); }}>Refresh settings</button><button className="button ghost" type="button" disabled={busy || saving} onClick={() => { setDraft(null); setMessage(null); resolveIssue("storage"); }}>Use current settings</button></p>}
    {saved && <p className="storage-saved" role="status"><Check size={13} />Policy saved. Cleanup continues safely in the background.</p>}
  </>;
}

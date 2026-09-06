import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";

export interface DiagnosticsStatus {
  state: string;
  bytes?: number;
  budget_bytes: number;
  dropped: number;
  queued: number;
  early_evictions?: number;
  last_ack_at?: number | null;
  ack_age_seconds?: number | null;
  build?: string | null;
  ranges?: Record<string, { rows: number; from: number | null; to: number | null }>;
}

const stateCopy: Record<string, string> = {
  starting: "Preparing history", recording: "Recording in the background",
  paused_storage: "Paused to protect storage", paused_error: "Recording needs attention",
  unavailable: "Recorder unavailable", disabled: "Recording disabled",
};

export function DiagnosticsHistory() {
  const [status, setStatus] = useState<DiagnosticsStatus | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    fetch("/api/v1/diagnostics", { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("Diagnostics unavailable");
        return await response.json() as DiagnosticsStatus;
      })
      .then(value => { if (!disposed) { setStatus(value); setError(false); } })
      .catch(() => { if (!disposed) setError(true); })
      .finally(() => window.clearTimeout(timeout));
    const timer = window.setTimeout(() => setRevision(value => value + 1), 60_000);
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer); window.clearTimeout(timeout); };
  }, [revision]);
  const detail = status?.ranges?.minute;
  const age = status?.ack_age_seconds ?? 0;
  const stale = status?.state === "recording" && age > 180;
  const label = error ? "History status unavailable" : stale ? "Recording delayed" : status ? stateCopy[status.state] ?? "History status unknown" : "Loading history status…";
  return <article className="card settings-card diagnostics-card">
    <div className="diagnostics-heading"><div><h2>Diagnostics history</h2><p>Local summaries for reviewing learning, trading activity and performance over time.</p></div><button type="button" className="button" aria-label="Refresh diagnostics status" onClick={() => setRevision(value => value + 1)}><RefreshCw size={15} /></button></div>
    <p role="status">{label}</p>
    <div className="diagnostics-facts"><strong>{status?.bytes == null ? "Usage not measured yet" : `${(status.bytes / 1048576).toFixed(1)} MiB used`}<small>Separate 512 MiB allowance</small></strong><strong>{detail?.rows ? `${detail.rows.toLocaleString()} detailed intervals` : status?.state === "disabled" ? "Retained history can still be exported" : "Waiting for the first interval"}<small>{detail?.from ? `Retained since ${new Date(detail.from * 1000).toLocaleString()}` : status?.state === "disabled" ? "Existing files are kept" : "Recording starts with this version"}</small></strong></div>
    <p className="storage-note">Targets: 30 days of minute summaries, 1 year of hourly summaries and 90 days of compact events. The byte limit takes priority. Storage is separate from the database budget above.</p>
    {!!(status?.dropped || status?.early_evictions || status?.queued) && <p className="storage-note">{status?.dropped ?? 0} skipped records · {status?.early_evictions ?? 0} intervals expired early · {status?.queued ?? 0} queued. Gaps stay visible.</p>}
    <div className="diagnostics-footer"><a className="button" href="/api/v1/diagnostics/export" download><Download size={15} />Download review history</a>{status?.build && <small title={status.build}>Build {status.build.slice(0, 12)}</small>}</div>
    <p className="storage-note">Works with this page closed. Summaries help compare evidence and identify problems; they are not training data or a complete trade replay.</p>
  </article>;
}

import { savedTimestampMicros } from "./evidenceTime";
import type { StorageStatus } from "./types";

function measurementAge(label: string, measuredAt: string | null | undefined, serverTime: string): string {
  const measured = savedTimestampMicros(measuredAt);
  const now = savedTimestampMicros(serverTime);
  if (measured === null || now === null) return `${label} measurement time unavailable.`;
  if (measured > now) return `${label} measurement time is ahead of the server clock.`;
  const seconds = Number((now - measured) / 1_000_000n);
  const age = seconds < 60 ? `${seconds}s` : seconds < 3600 ? `${Math.floor(seconds / 60)}m` : `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`;
  return `${label} measured ${age} ago.`;
}

/** Describe saved measurements, without inferring progress or causing new reads. */
export function storagePresentation(storage: StorageStatus, serverTime: string) {
  const cleanup = storage.maintenance;
  const now = savedTimestampMicros(serverTime);
  const historyAt = savedTimestampMicros(cleanup?.history_checked_at);
  const oldest = savedTimestampMicros(cleanup?.oldest_retained_trade_at);
  let history = "Raw history measurement unavailable.";
  if (historyAt !== null && now !== null && historyAt <= now) {
    if (cleanup?.oldest_retained_trade_at === null) {
      history = "No raw trades were retained at the last history check.";
    } else if (oldest !== null && oldest <= historyAt) {
      const ageHours = Number(historyAt - oldest) / 3_600_000_000;
      const behind = ageHours > storage.raw_trade_retention_hours;
      const age = behind && Math.floor(ageHours) === storage.raw_trade_retention_hours
        ? `over ${storage.raw_trade_retention_hours}` : String(Math.floor(ageHours));
      history = `${behind ? "History is behind target: " : "Last history check: "}oldest raw trade was ${age} hours old; target ${storage.raw_trade_retention_hours} hours.`;
    } else if (oldest !== null) {
      history = "Raw history measurement has inconsistent timestamps.";
    }
  }
  const status = cleanup?.budget_state === "capacity_unknown"
    ? "Storage capacity could not be refreshed yet. Showing the last measurement; cleanup will retry."
    : cleanup?.active
      ? "Background cleanup pass in progress."
      : cleanup?.deferred_reason
        ? "Background cleanup is deferred and will retry."
        : cleanup?.budget_state === "retained_evidence_above_target"
          ? "Protected trading and learning records exceed this target and were kept."
          : cleanup?.requested
            ? "Background cleanup has more work scheduled."
            : cleanup?.last_completed_at
              ? "Last cleanup pass completed. Measurement times are shown below."
              : "Waiting for a completed storage check.";
  return {
    status, history,
    capacityAge: measurementAge("Capacity", cleanup?.capacity_checked_at, serverTime),
    historyAge: measurementAge("History", cleanup?.history_checked_at, serverTime),
  };
}

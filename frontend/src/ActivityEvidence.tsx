import type { DataValue, FeatureSnapshot } from "./types";
import { savedEvidenceAge } from "./evidenceTime";

const rows = [
  ["buy_quote_volume_ratio_5m", "Buy share of volume (5m)", "percent"],
  ["signed_net_quote_flow_ratio_5m", "Net buy − sell flow (5m)", "signed"],
  ["meaningful_trade_count_1m", "Trades ≥ 0.01 SOL (1m)", "count"],
  ["meaningful_trade_count_5m", "Trades ≥ 0.01 SOL (5m)", "count"],
  ["meaningful_trade_wallet_count_5m", "Wallets with a trade ≥ 0.01 SOL (5m)", "count"],
  ["net_buy_wallet_count_5m", "Wallets net buying ≥ 0.01 SOL (5m)", "count"],
  ["trade_amount_coverage_5m", "Trades with known amounts (5m)", "percent"],
] as const;

function display(item: DataValue | undefined, kind: string) {
  if (!item) return "Not recorded";
  const value = item.value;
  if (item.missing_reason || item.quality !== 1 || item.unit !== (kind === "count" ? "count" : "fraction") || typeof value !== "number" || !Number.isFinite(value)) return "Unknown";
  if (kind === "count") return Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString() : "Unknown";
  if (value > 1 || value < (kind === "signed" ? -1 : 0)) return "Unknown";
  return `${kind === "signed" && value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

/** Saved observations only; absence never means zero activity or a clean market. */
export default function ActivityEvidence({ snapshot, decisionAt }: { snapshot: FeatureSnapshot; decisionAt?: string }) {
  const values = snapshot.values;
  if (!rows.some(([key]) => key in values)) return <p>Trade-value breakdown was not recorded for this decision.</p>;
  const complete = values.integrity_window_complete?.value === true
    && values.integrity_window_complete.quality === 1
    && !values.integrity_window_complete.missing_reason
    && values.trade_buffer_saturated?.value === false
    && values.trade_buffer_saturated.quality === 1
    && !values.trade_buffer_saturated.missing_reason;
  return <>
    <h3>Trade counts and value</h3>
    <p>Observed SOL flow, separate from the Baseline score. Net flow is buys minus sells divided by total volume. Wallet counts do not establish independent traders or rule out manipulation.</p>
    <div className="evidence-grid">{rows.map(([key, label, kind]) => {
      const item = values[key];
      return <div key={key}><span>{label}</span><strong>{display(item, kind)}</strong><small>{item
        ? `${savedEvidenceAge(item.as_of, decisionAt)}${item.missing_reason ? ` · ${item.missing_reason.replaceAll("_", " ")}` : ""}`
        : "Older evidence is not reconstructed"}</small></div>;
    })}</div>
    <p>{complete ? "The saved continuity check passed." : "Complete stream coverage is not established for this saved window."} These are observed-window measurements. The 0.01 SOL cutoff describes trade size; it is not a safety gate or a new learning input.</p>
  </>;
}

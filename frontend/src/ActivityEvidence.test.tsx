import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import ActivityEvidence from "./ActivityEvidence";
import type { DataValue, FeatureSnapshot } from "./types";

afterEach(cleanup);

const item = (value: DataValue["value"], unit = "fraction"): DataValue => ({ value, unit, quality: 1, freshness_seconds: 0.4, as_of: "2026-09-20T10:00:00Z", sources: ["test"], missing_reason: null });
const snapshot = (values: Record<string, DataValue>): FeatureSnapshot => ({ mint: "test", symbol: "TEST", name: "Test", venue: "pump_curve", computed_at: "2026-09-20T10:00:00Z", values, hard_flags: [], data_confidence: 1 });
const displayed = (label: string) => screen.getByText(label).nextElementSibling;

test("counts, traded value and signed sell pressure remain distinct with preserved provenance", () => {
  const saved = snapshot({ buy_ratio_5m: item(0.95), buy_quote_volume_ratio_5m: item(0.12), signed_net_quote_flow_ratio_5m: item(-0.76), meaningful_trade_count_1m: item(0, "count") });
  const before = JSON.stringify(saved);
  render(<ActivityEvidence snapshot={saved} decisionAt="2026-09-20T10:00:02.400Z" />);
  expect(displayed("Buy share of volume (5m)")).toHaveTextContent("12.0%");
  expect(displayed("Net buy − sell flow (5m)")).toHaveTextContent("-76.0%");
  expect(displayed("Trades ≥ 0.01 SOL (1m)")).toHaveTextContent("0");
  expect(screen.getAllByText("2.4s old at decision")).toHaveLength(3);
  expect(screen.getByText(/Complete stream coverage is not established/)).toBeInTheDocument();
  expect(JSON.stringify(saved)).toBe(before);
});

test.each([
  [undefined, "2026-09-20T10:00:00Z", "Age unavailable"],
  ["bad", "2026-09-20T10:00:00Z", "Age unavailable"],
  ["2026-09-20T10:00:00", "2026-09-20T10:00:00Z", "Age unavailable"],
  ["2026-09-20T10:00:00Z", "bad", "Age unavailable"],
  ["2026-09-20T10:00:00Z", "2026-09-20T10:00:00", "Age unavailable"],
  ["2026-09-20T10:00:00Z", "2026-09-20T10:00:00.001Z", "Measurement clock is after decision"],
  ["2026-09-20T11:00:03+01:00", "2026-09-20T10:00:00Z", "3.0s old at decision"],
  ["2026-09-20T10:00:00Z", "2026-09-20T10:00:00Z", "0.0s old at decision"],
])("saved clocks remain honest: %s / %s", (decisionAt, asOf, expected) => {
  render(<ActivityEvidence decisionAt={decisionAt} snapshot={snapshot({ buy_quote_volume_ratio_5m: { ...item(0.5), as_of: asOf! } })} />);
  expect(screen.getByText(expected!)).toBeInTheDocument();
});

test("older records are not silently reconstructed as zero or clean", () => {
  render(<ActivityEvidence snapshot={snapshot({})} />);
  expect(screen.getByText(/not recorded for this decision/)).toBeInTheDocument();
  expect(screen.queryByText("0")).not.toBeInTheDocument();
});

test.each([null, true, "0.7", NaN, Infinity, -0.1, 1.1])("invalid value share is unknown: %s", value => {
  render(<ActivityEvidence snapshot={snapshot({ buy_quote_volume_ratio_5m: item(value) })} />);
  expect(displayed("Buy share of volume (5m)")).toHaveTextContent("Unknown");
});

test.each([{ quality: 0.99 }, { missing_reason: "trade_amount_unavailable" }, { unit: "SOL" }])("partial or incompatible value evidence stays unknown: %s", patch => {
  render(<ActivityEvidence snapshot={snapshot({ buy_quote_volume_ratio_5m: { ...item(0.9), ...patch } })} />);
  expect(displayed("Buy share of volume (5m)")).toHaveTextContent("Unknown");
});

test.each([true, false, null])("buffer coverage remains separate from an observed number: %s", saturated => {
  render(<ActivityEvidence snapshot={snapshot({ buy_quote_volume_ratio_5m: item(0.6), integrity_window_complete: item(true, "boolean"), trade_buffer_saturated: item(saturated, "boolean") })} />);
  expect(displayed("Buy share of volume (5m)")).toHaveTextContent("60.0%");
  expect(screen.getByText(saturated === false ? /saved continuity check passed/ : /Complete stream coverage is not established/)).toBeInTheDocument();
});

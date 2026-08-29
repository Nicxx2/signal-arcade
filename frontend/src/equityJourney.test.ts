import { describe, expect, test } from "vitest";
import { buildEquityJourney, unchangedEquitySeconds } from "./equityJourney";
import type { EquityPoint } from "./types";

function point(second: number, equity: number): EquityPoint {
  return {
    recorded_at: new Date(Date.UTC(2026, 7, 29, 0, 0, second)).toISOString(),
    equity_lamports: equity,
    cash_lamports: equity,
  };
}

describe("equity journey", () => {
  test("collapses an unchanged plateau without changing the source points", () => {
    const source = [point(0, 100), point(1, 90), point(2, 90), point(3, 90)];
    expect(buildEquityJourney(source).map((item) => item.equity_lamports)).toEqual([100, 90]);
    expect(source).toHaveLength(4);
    expect(unchangedEquitySeconds(source)).toBe(2);
  });

  test("handles empty, one-point, and completely flat histories", () => {
    expect(buildEquityJourney([])).toEqual([]);
    expect(buildEquityJourney([point(0, 100)])).toHaveLength(1);
    expect(buildEquityJourney([point(0, 100), point(10, 100)])).toHaveLength(1);
  });

  test("bounds long histories while retaining endpoints and bucket extremes", () => {
    const source = Array.from({ length: 1_000 }, (_, index) => point(index % 60, index % 2 ? 50 + index : 200 - index));
    const journey = buildEquityJourney(source, 40);
    expect(journey.length).toBeLessThanOrEqual(40);
    expect(journey[0]).toBe(source[0]);
    expect(journey.at(-1)).toBe(source.at(-1));
    expect(Math.min(...journey.map((item) => item.equity_lamports))).toBe(Math.min(...source.map((item) => item.equity_lamports)));
    expect(Math.max(...journey.map((item) => item.equity_lamports))).toBe(Math.max(...source.map((item) => item.equity_lamports)));
  });

  test("does not invent a duration when timestamps are invalid", () => {
    const invalid = [{ ...point(0, 100), recorded_at: "invalid" }, { ...point(1, 100), recorded_at: "also-invalid" }];
    expect(unchangedEquitySeconds(invalid)).toBe(0);
  });
});

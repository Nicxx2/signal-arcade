import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { EquityChart, validEquityPoints } from "./EquityChart";
import type { EquityPoint } from "./types";

afterEach(cleanup);
const points: EquityPoint[] = [100, 160, 110].map((value, index) => ({
  recorded_at: new Date(Date.UTC(2026, 8, 6, index)).toISOString(),
  equity_lamports: value * 1e6, cash_lamports: (value - 10) * 1e6,
}));
const props = { points, currency: "USDC" as const, decimals: 6, starting: 100e6, peak: 180e6 };

describe("equity inspection", () => {
  test("does not fabricate a chart from empty or invalid data", () => {
    render(<EquityChart {...props} points={[{ ...points[0]!, recorded_at: "invalid" }]} />);
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.getByText("Waiting for the first equity checkpoint.")).toBeTruthy();
    expect(validEquityPoints([{ ...points[0]!, equity_lamports: NaN }])).toEqual([]);
  });
  test("uses saved peak and keyboard inspection of actual equity and cash", () => {
    render(<EquityChart {...props} />);
    expect(screen.getByText("180.00 USDC")).toBeTruthy();
    const chart = screen.getByRole("slider");
    fireEvent.keyDown(chart, { key: "Home" });
    expect(chart.getAttribute("aria-valuenow")).toBe("1");
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(chart.getAttribute("aria-valuetext")).toContain("160.00 USDC");
    expect(screen.getByText(/150.00 USDC cash/)).toBeTruthy();
    fireEvent.keyDown(chart, { key: "End" });
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(chart.getAttribute("aria-valuenow")).toBe("3");
  });
  test("refresh retains the selected checkpoint identity and handles its removal", () => {
    const view = render(<EquityChart {...props} />);
    const chart = screen.getByRole("slider");
    fireEvent.keyDown(chart, { key: "Home" });
    view.rerender(<EquityChart {...props} points={[...points, { ...points[2]!, recorded_at: "2026-09-06T03:00:00Z", equity_lamports: 120e6 }]} />);
    expect(chart.getAttribute("aria-valuenow")).toBe("1");
    view.rerender(<EquityChart {...props} points={points.slice(1)} />);
    expect(chart.getAttribute("aria-valuetext")).toContain("110.00 USDC");
  });
  test("distinct checkpoints at the same timestamp remain selectable across refreshes", () => {
    const simultaneous = points.map((point) => ({ ...point, recorded_at: points[0]!.recorded_at }));
    const view = render(<EquityChart {...props} points={simultaneous} />);
    const chart = screen.getByRole("slider");
    fireEvent.keyDown(chart, { key: "Home" });
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(chart.getAttribute("aria-valuenow")).toBe("2");
    expect(chart.getAttribute("aria-valuetext")).toContain("160.00 USDC");
    view.rerender(<EquityChart {...props} points={simultaneous.slice(1)} />);
    expect(chart.getAttribute("aria-valuenow")).toBe("1");
    expect(chart.getAttribute("aria-valuetext")).toContain("160.00 USDC");
    fireEvent.keyDown(chart, { key: "End" });
    expect(chart.getAttribute("aria-valuetext")).toContain("110.00 USDC");
  });
  test("Timeline can step through repeated identical observations", () => {
    render(<EquityChart {...props} points={[points[0]!, { ...points[0]! }, points[1]!]} />);
    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));
    const chart = screen.getByRole("slider");
    fireEvent.keyDown(chart, { key: "Home" });
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(chart.getAttribute("aria-valuenow")).toBe("2");
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(chart.getAttribute("aria-valuenow")).toBe("3");
    expect(chart.getAttribute("aria-valuetext")).toContain("160.00 USDC");
  });
  test("hourly close is labelled as an interval with its range, never an exact observation", () => {
    render(<EquityChart {...props} points={[{ ...points[0]!, kind: "hourly_close", period_end: "2026-09-06T01:00:00Z", high_equity_lamports: 140e6, low_equity_lamports: 90e6 }]} />);
    fireEvent.focus(screen.getByRole("slider"));
    expect(screen.getByText(/Hourly close/)).toBeTruthy();
    expect(screen.getByText(/Hour range 90.00 USDC–140.00 USDC/)).toBeTruthy();
    expect(screen.getByText(/exact checkpoint times are unavailable/)).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Chart help" }));
    expect(screen.getByText(/exact checkpoint times are unavailable/)).toBeVisible();
  });
  test("flat one-point SOL history has no invalid coordinates and supports Timeline", () => {
    const { container } = render(<EquityChart {...props} currency="SOL" decimals={9} points={[points[0]!]} />);
    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    expect(screen.getByRole("slider").getAttribute("aria-valuetext")).toContain("0.10 SOL");
  });
});

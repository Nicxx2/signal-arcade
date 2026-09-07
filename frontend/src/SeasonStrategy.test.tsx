import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SeasonStrategy from "./SeasonStrategy";
import type { SeasonStrategyUsage } from "./types";

afterEach(cleanup);

const mixed: SeasonStrategyUsage = {
  status: "mixed", complete_from_start: true, baseline_observed: true,
  tracking_started_at: "2026-09-06T10:00:00Z", first_baseline_at: "2026-09-06T10:01:00Z",
  skills_observed: ["entry", "sizing"],
  participants: [
    { kind: "champion", skill: "entry", version: "entry-v1", name: "Clear Beacon", first_used_at: "2026-09-06T11:00:00Z" },
    { kind: "champion", skill: "sizing", version: "sizing-v2", name: "Quiet Balancer", first_used_at: "2026-09-06T12:00:00Z" },
  ],
};

describe("recorded season strategy", () => {
  it("keeps missing historical attribution unknown rather than assuming Baseline", () => {
    render(<SeasonStrategy />);
    expect(screen.getByText("Influence not recorded")).toBeInTheDocument();
    expect(screen.queryByText("Baseline only")).not.toBeInTheDocument();
  });

  it("distinguishes no decisions from confirmed Baseline-only participation", () => {
    const { rerender } = render(<SeasonStrategy usage={{ status: "no_decisions", complete_from_start: true, participants: [] }} />);
    expect(screen.getByText("No decisions recorded")).toBeInTheDocument();
    rerender(<SeasonStrategy usage={{ status: "baseline", complete_from_start: true, participants: [] }} />);
    expect(screen.getByText("Baseline only")).toBeInTheDocument();
  });

  it("exposes stable historical identities and describes actual use without claiming activation times", () => {
    const { container } = render(<SeasonStrategy usage={mixed} />);
    expect(screen.getByText("Mixed · Champion support")).toBeInTheDocument();
    expect(screen.getByText("Entry + Sizing")).toBeInTheDocument();
    const summary = container.querySelector("summary")!;
    fireEvent.click(summary);
    expect(screen.getByText("Clear Beacon · Entry")).toBeInTheDocument();
    expect(screen.getByText("sizing-v2")).toBeInTheDocument();
    expect(screen.getByText(/First use is not an activation or suspension timestamp/)).toBeInTheDocument();
  });

  it("keeps partial and bounded histories explicit", () => {
    render(<SeasonStrategy usage={{ ...mixed, complete_from_start: false, details_limited: true }} />);
    expect(screen.getByText("Partial history")).toBeInTheDocument();
    expect(screen.getByText(/Earlier participation is unknown/)).toBeInTheDocument();
    expect(screen.getByText(/first 128 participants/)).toBeInTheDocument();
  });

  it("does not call a standalone AI veto champion influence", () => {
    render(<SeasonStrategy usage={{ status: "assisted", complete_from_start: true, ai_observed: true, participants: [{ kind: "ai_critic", skill: "", name: "Local AI critic", version: "ai-critic-v4", first_used_at: "2026-09-06T11:00:00Z" }] }} />);
    expect(screen.getByText("AI critic support")).toBeInTheDocument();
    expect(screen.queryByText("Champion support")).not.toBeInTheDocument();
  });

  it("keeps incomplete participant metadata explicit alongside confirmed use", () => {
    render(<SeasonStrategy usage={{ ...mixed, unattributed_use: true }} />);
    expect(screen.getByText("Partial history")).toBeInTheDocument();
    expect(screen.getByText(/Some recorded use had incomplete participant details/)).toBeInTheDocument();
  });
});

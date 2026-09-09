import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { SkillSuspension } from "./SkillSuspension";
import type { ChallengerSkillStatus } from "./types";

afterEach(cleanup);
const suspension: NonNullable<ChallengerSkillStatus["suspension"]> = {
  reason: "degraded", since: "2026-09-08T12:00:00Z", status: "collecting",
  enrolled_count: 60, observed_count: 44, usable_count: 43, availability_fraction: 43 / 44,
  window_size: 60, restored_at: null,
};

test("suspension is compact and distinguishes recovery from learning and a new crown", () => {
  const { container } = render(<SkillSuspension skill={{ state: "suspended", suspension }} paused={false} supportAllowed />);
  expect(container.querySelector("details")).not.toHaveAttribute("open");
  expect(screen.getByText("Support suspended · learning continues")).toBeInTheDocument();
  expect(screen.getByText(/60 \/ 60 enrolled · 44 resolved · 43 usable/)).toHaveTextContent("70% coverage");
  expect(screen.getByText(/Recovery does not award a new crown/)).toBeInTheDocument();
});

test("paused and disabled support do not promise automatic recovery", () => {
  render(<SkillSuspension skill={{ state: "suspended", suspension }} paused supportAllowed={false} />);
  expect(screen.getByText("Support suspended · learning paused")).toBeInTheDocument();
  expect(screen.getByText(/Automatic support is off/)).toBeInTheDocument();
  expect(screen.queryByText(/New candidates and shadow comparisons continue/)).not.toBeInTheDocument();
});

test("failed proof and legacy missing reasons require replacement without inventing a cause", () => {
  render(<SkillSuspension skill={{ state: "suspended", suspension: null }} paused={false} supportAllowed />);
  expect(screen.getByText(/A newly proved replacement/)).toBeInTheDocument();
  expect(screen.queryByText(/Recent evidence showed harm/)).not.toBeInTheDocument();
});

test("restored skills do not keep a suspension warning", () => {
  const { container } = render(<SkillSuspension skill={{ state: "active", suspension: { ...suspension, status: "restored" } }} paused={false} supportAllowed />);
  expect(container).toBeEmptyDOMElement();
});

test.each([undefined, ["advantage", "harm"], ["future_check"]])("failed trial shows saved checks without inventing legacy results: %j", (failed_checks) => {
  render(<SkillSuspension skill={{ state: "suspended", suspension: { ...suspension, status: "failed", observed_count: 60, usable_count: 47, failed_checks } }} paused={false} supportAllowed />);
  expect(screen.getByText(/Recovery trial finished/)).toHaveTextContent("47 usable of 60 resolved");
  expect(screen.getByText(/This fixed trial will not restart/)).toBeInTheDocument();
  expect(screen.getByText(failed_checks?.includes("advantage") ? /Checks not met: safe advantage, harm limit/ : /individual results were not recorded/)).toBeInTheDocument();
});

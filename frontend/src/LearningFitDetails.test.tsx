import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import LearningFitDetails from "./LearningFitDetails";
import { artifact } from "./championArena/fixtures";
import type { ChallengerSkillStatus } from "./types";

afterEach(cleanup);
type Artifact = NonNullable<ChallengerSkillStatus["latest_candidate"]>;
const saved = (): Artifact => ({ ...artifact("saved", "Saved candidate"), schema_version: "challenger-skill-v2", skill: "entry", sample_count: 498, training_count: 299, validation_count: 166, embargoed_count: 33, training_cutoff_at: "2026-09-19T12:00:00Z", evidence_started_at: "2026-09-19T10:00:00Z", evidence_ended_at: "2026-09-19T13:00:00Z" });
const value = (label: string) => screen.getByText(label, { selector: "dt" }).nextElementSibling;

test("Discovery shows the exact saved split without calling 1,000 rows training examples", () => {
  const item = saved(), before = JSON.stringify(item);
  render(<LearningFitDetails artifact={item} />);
  expect(value("Usable Discovery outcomes")).toHaveTextContent("498");
  expect(value("Training rows")).toHaveTextContent("299");
  expect(value("Validation rows")).toHaveTextContent("166");
  expect(value("Excluded for chronology")).toHaveTextContent("33");
  expect(value("Validation starts")).toHaveTextContent(new Date(item.training_cutoff_at!).toLocaleString());
  expect(screen.getByText(/period describes usable evidence/)).toBeInTheDocument();
  expect(JSON.stringify(item)).toBe(before);
});

test.each([undefined, null, "bad", "2026-09-19T10:00:00", "2026-09-20T10:00:00Z", "2026-02-30T10:00:00Z", "2025-02-29T10:00:00Z", "1900-02-29T10:00:00Z", "2026-04-31T10:00:00Z", "2026-09-19T24:00:00Z"])("absent, invalid or reversed evidence dates stay unavailable: %s", start => {
  render(<LearningFitDetails artifact={{ ...saved(), evidence_started_at: start }} />);
  expect(value("Usable evidence period")).toHaveTextContent("Unavailable");
});

test.each([
  ["1970-01-01T00:00:00Z", "1970-01-01T00:00:00Z"],
  ["2000-02-29T12:00:00Z", "2000-02-29T13:00:00Z"],
  ["2024-02-29T12:00:00.123456Z", "2024-02-29T13:00:00Z"],
  ["2026-09-20T00:00:00+01:00", "2026-09-19T23:00:00Z"],
])("valid saved dates preserve leap days, precision and timezone ordering: %s", (start, end) => {
  render(<LearningFitDetails artifact={{ ...saved(), evidence_started_at: start, evidence_ended_at: end }} />);
  expect(value("Usable evidence period")).toHaveTextContent(`${new Date(start).toLocaleString()} – ${new Date(end).toLocaleString()}`);
});

test.each(["evidence_ended_at", "training_cutoff_at"])("impossible dates are unavailable in every saved date field: %s", field => {
  render(<LearningFitDetails artifact={{ ...saved(), [field]: "2026-02-30T12:00:00Z" }} />);
  expect(value(field === "training_cutoff_at" ? "Validation starts" : "Usable evidence period")).toHaveTextContent("Unavailable");
});

test.each([undefined, null, -1, 1.5, NaN, Infinity, true, "50"])("invalid historical counts are not displayed as real evidence: %s", count => {
  render(<LearningFitDetails artifact={{ ...saved(), training_count: count as number }} />);
  expect(value("Training rows")).toHaveTextContent("Unavailable");
});

test("Sizing never infers chronology exclusions from missing targets", () => {
  render(<LearningFitDetails artifact={{ ...saved(), skill: "sizing", sample_count: 1000, training_count: 510, validation_count: 333, embargoed_count: 12 }} />);
  expect(value("Policy observations")).toHaveTextContent("1,000");
  expect(value("Excluded for chronology")).toHaveTextContent("12");
  expect(screen.getByText(/without a usable target are separate/)).toBeInTheDocument();
});

test("contextual Exit labels a cohort instead of inventing per-horizon fit counts", () => {
  render(<LearningFitDetails artifact={{ ...saved(), skill: "exit", recipe_version: "exit-context-v1" }} />);
  expect(value("Training cohort")).toHaveTextContent("299");
  expect(screen.getByText(/Per-horizon fit counts were not saved/)).toBeInTheDocument();
  expect(screen.queryByText("Training rows")).toBeNull();
});

test("deterministic Exit describes selection and Coach describes independent study populations", () => {
  const view = render(<LearningFitDetails artifact={{ ...saved(), skill: "exit", model_family: "deterministic", recipe_version: "earlier-review-v1" }} />);
  expect(value("Timing selection rows")).toHaveTextContent("299");
  view.rerender(<LearningFitDetails artifact={{ ...saved(), schema_version: "challenger-skill-coach-v1", recipe_version: "coach-policy-v1", training_count: 21, validation_count: 60, sample_count: 60 }} />);
  expect(value("Historical screening outcomes")).toHaveTextContent("21");
  expect(value("Forward usable outcomes")).toHaveTextContent("60");
  expect(screen.queryByText("Validation rows")).toBeNull();
  expect(screen.queryByText("Excluded for chronology")).toBeNull();
  expect(screen.getByText(/not a regression training split/)).toBeInTheDocument();
});

test("unknown historical format does not acquire modern population definitions", () => {
  render(<LearningFitDetails artifact={{ ...saved(), schema_version: undefined, evidence_started_at: null, evidence_ended_at: null, training_cutoff_at: null }} />);
  expect(value("Recorded evidence period")).toHaveTextContent("Unavailable");
  expect(value("Recorded cutoff")).toHaveTextContent("Unavailable");
  expect(screen.getByText(/Detailed population definitions are unavailable/)).toBeInTheDocument();
});

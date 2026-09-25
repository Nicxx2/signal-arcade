import { expect, test } from "vitest";
import { savedEvidenceAge } from "./evidenceTime";

test.each([
  ["2026-09-20T10:00:00.000001Z", "2026-09-20T10:00:00.000000Z", "Measurement clock is after decision"],
  ["2026-09-20T10:00:00.999999Z", "2026-09-20T10:00:00.999998Z", "Measurement clock is after decision"],
  ["2026-09-20T11:00:00.000001+01:00", "2026-09-20T10:00:00Z", "Measurement clock is after decision"],
  ["2026-02-30T10:00:00Z", "2026-03-02T10:00:01Z", "Age unavailable"],
  ["2026-02-29T10:00:00Z", "2026-03-01T10:00:01Z", "Age unavailable"],
  ["2024-02-29T10:00:00Z", "2024-02-29T10:00:01Z", "1.0s old at decision"],
  ["2026-09-20T24:00:00Z", "2026-09-21T00:00:01Z", "Age unavailable"],
  ["2026-09-20T10:00:00.999999Z", "2026-09-20T10:00:01.000000Z", "0.0s old at decision"],
  ["2026-09-20T10:00:00.1Z", "2026-09-20T10:00:00.2Z", "0.1s old at decision"],
  ["2026-09-20T23:00:00+23:00", "2026-09-20T00:00:01Z", "1.0s old at decision"],
  ["2026-09-20T10:00:00Z", "2026-09-20T10:00:00+24:00", "Age unavailable"],
  ["2026-09-20T10:00:00Z", "2026-09-20T10:00:00+01:60", "Age unavailable"],
])("original clocks stay exact: %s / %s", (asOf, at, expected) => {
  expect(savedEvidenceAge(asOf, at)).toBe(expected);
});

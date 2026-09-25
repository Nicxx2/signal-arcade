import { expect, test } from "vitest";
import { storagePresentation } from "./storagePresentation";
import type { StorageStatus } from "./types";

const now = "2026-09-24T13:00:00Z";
const storage = {
  raw_trade_retention_hours: 24,
  maintenance: {
    active: false, requested: true, budget_state: "cleanup_needed", deferred_reason: null,
    capacity_checked_at: "2026-09-24T12:59:45Z", history_checked_at: "2026-09-24T12:50:00Z",
    oldest_retained_trade_at: "2026-09-22T20:50:00Z",
  },
} as StorageStatus;

test("uses each original measurement time and does not claim catch-up", () => {
  const view = storagePresentation(storage, now);
  expect(view.capacityAge).toBe("Capacity measured 15s ago.");
  expect(view.historyAge).toBe("History measured 10m ago.");
  expect(view.history).toBe("History is behind target: oldest raw trade was 40 hours old; target 24 hours.");
  expect(JSON.stringify(view)).not.toMatch(/catching up|healthy|ready/i);
});

test("aging an old snapshot cannot age the original measured history", () => {
  const later = storagePresentation(storage, "2026-09-25T13:00:00Z");
  expect(later.history).toContain("was 40 hours old");
  expect(later.historyAge).toBe("History measured 24h 10m ago.");
});

test.each([
  ["2026-09-23T12:50:00Z", "Last history check: oldest raw trade was 24 hours old"],
  ["2026-09-23T12:49:59.999999Z", "History is behind target: oldest raw trade was over 24 hours old"],
  ["2026-09-23T12:50:00.000001Z", "Last history check: oldest raw trade was 23 hours old"],
])("the retention boundary stays honest at %s", (oldest, expected) => {
  const view = storagePresentation({ ...storage, maintenance: { ...storage.maintenance!, oldest_retained_trade_at: oldest } }, now);
  expect(view.history).toContain(expected);
});

test.each([undefined, null, "invalid", "2026-02-30T00:00:00Z", "2026-09-24T12:00:00"])("unknown time %s is not fresh or empty", value => {
  const view = storagePresentation({ ...storage, maintenance: { ...storage.maintenance!, capacity_checked_at: value ?? undefined, history_checked_at: value } }, now);
  expect(view.capacityAge).toContain("unavailable");
  expect(view.historyAge).toContain("unavailable");
  expect(view.history).toBe("Raw history measurement unavailable.");
});

test("future clocks stay unknown, including microsecond differences", () => {
  const view = storagePresentation({ ...storage, maintenance: { ...storage.maintenance!, capacity_checked_at: "2026-09-24T14:00:00.000001+01:00", history_checked_at: "2026-09-24T13:00:01Z" } }, now);
  expect(view.capacityAge).toContain("ahead of the server clock");
  expect(view.history).toContain("unavailable");
});

test("empty history needs a completed valid measurement", () => {
  const empty = { ...storage, maintenance: { ...storage.maintenance!, oldest_retained_trade_at: null } };
  expect(storagePresentation(empty, now).history).toContain("No raw trades were retained at the last history check");
  expect(storagePresentation({ ...empty, maintenance: { ...empty.maintenance, history_checked_at: null } }, now).history).toContain("unavailable");
});

test("a retry does not hide unknown capacity; protected-only and pending work are distinct", () => {
  expect(storagePresentation({ ...storage, maintenance: { ...storage.maintenance!, active: true, budget_state: "capacity_unknown" } }, now).status).toContain("could not be refreshed");
  expect(storagePresentation({ ...storage, maintenance: { ...storage.maintenance!, budget_state: "retained_evidence_above_target" } }, now).status).toContain("Protected trading and learning records");
  expect(storagePresentation(storage, now).status).toContain("more work scheduled");
});

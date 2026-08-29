import { expect, test } from "vitest";
import {
  INITIAL_SYSTEM_STATUS,
  friendlyError,
  systemStatusReducer,
} from "./systemStatus";

test("deduplicates repeated failures and resolves them after recovery", () => {
  const first = systemStatusReducer(INITIAL_SYSTEM_STATUS, {
    type: "report",
    scope: "server",
    title: "App server unavailable",
    detail: "Temporarily unreachable",
    at: 1_000,
  });
  const repeated = systemStatusReducer(first, {
    type: "report",
    scope: "server",
    title: "App server unavailable",
    detail: "Temporarily unreachable",
    at: 2_000,
  });

  expect(repeated.issues).toHaveLength(1);
  expect(repeated.issues[0]?.occurrences).toBe(2);
  expect(repeated.issues[0]?.lastSeenAt).toBe(2_000);

  const recovered = systemStatusReducer(repeated, {
    type: "resolve",
    scope: "server",
    at: 3_000,
    serverHealthy: true,
  });
  expect(recovered.activeByScope.server).toBeUndefined();
  expect(recovered.issues[0]?.resolvedAt).toBe(3_000);
  expect(recovered.lastSuccessAt).toBe(3_000);
});

test("a healthy snapshot moves one-off action failures into history", () => {
  const failedAction = systemStatusReducer(INITIAL_SYSTEM_STATUS, {
    type: "report",
    scope: "risk",
    title: "Risk mode was not changed",
    detail: "Request failed",
    at: 1_000,
  });
  const recovered = systemStatusReducer(failedAction, {
    type: "resolve",
    scope: "server",
    at: 2_000,
    serverHealthy: true,
  });

  expect(recovered.activeByScope.risk).toBeUndefined();
  expect(recovered.issues[0]?.resolvedAt).toBe(2_000);
});

test("turns raw browser network failures into a useful message", () => {
  expect(friendlyError(new TypeError("Failed to fetch"))).toBe(
    "The app server is temporarily unreachable. Signal Arcade will keep retrying quietly.",
  );
});

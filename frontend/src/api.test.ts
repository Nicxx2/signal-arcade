import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());
test("already-aborted history requests propagate cancellation before fetch", async () => {
  const controller = new AbortController(); controller.abort();
  const fetcher = vi.fn(async (_url: string, options: RequestInit) => {
    expect(options.signal?.aborted).toBe(true); throw new DOMException("Aborted", "AbortError");
  });
  vi.stubGlobal("fetch", fetcher);
  await expect(api.championJourney("old", controller.signal, 50)).rejects.toMatchObject({ name: "AbortError" });
});
test("history pages stay read-only, clamp limits and encode cursors", async () => {
  const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ events: [], total: 0, next_cursor: null })));
  vi.stubGlobal("fetch", fetcher);
  await api.championJourney("x&risk=safe", undefined, 500); await api.championJourney(undefined, undefined, NaN);
  expect(fetcher.mock.calls[0]).toEqual(["/api/v1/learning/champion-journey?limit=50&cursor=x%26risk%3Dsafe", expect.not.objectContaining({ method: "POST" })]);
  expect(fetcher.mock.calls[1]![0]).toContain("limit=8");
});
test("obsolete history cursors retain their HTTP status for a safe UI reset", async () => {
  vi.stubGlobal("fetch", async () => ({ ok: false, status: 409, json: async () => ({ detail: "Cohort changed" }) }));
  await expect(api.championJourney("obsolete")).rejects.toEqual(new ApiError("Cohort changed", 409));
});

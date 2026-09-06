import { expect, test } from "vitest";
import { mergeHistoryWindow, HISTORY_WINDOW } from "./history";
import { eventFixture } from "./fixtures";
import { displaySignatures, makeFighter } from "./model";

test("paging is deduplicated and bounded without losing access to successively older records", () => {
  let window: ReturnType<typeof mergeHistoryWindow> = [];
  for (let page = 0; page < 100; page++) {
    const events = Array.from({ length: 8 }, (_, i) => ({ ...eventFixture(), event_id: `event-${page * 8 + i}`, occurred_at: new Date(1_700_000_000_000 - (page * 8 + i) * 1000).toISOString() }));
    window = mergeHistoryWindow(window, [...events, events[0]!]);
    expect(window.length).toBeLessThanOrEqual(HISTORY_WINDOW);
  }
  expect(window[0]!.event_id).toBe("event-736"); expect(window.at(-1)!.event_id).toBe("event-799");
});
test("cosmetic suffix collisions fall back to complete immutable identities", () => {
  const a = makeFighter("full-id-a", "Same name", "linear", "entry"), b = { ...makeFighter("full-id-b", "Same name", "linear", "entry"), signature: a.signature };
  expect(displaySignatures(a, b)).toEqual([a.id, b.id]);
});

import type { ChallengerChampionEvent } from "../types";

export const HISTORY_WINDOW = 64;
// The current snapshot supplies the newest events separately. Retain a bounded, older window
// while the user pages toward the past; the cursor continues to expose all stored records.
export function mergeHistoryWindow(current: ChallengerChampionEvent[], page: ChallengerChampionEvent[]) {
  const unique = new Map(current.map((event) => [event.event_id, event]));
  page.forEach((event) => unique.set(event.event_id, event));
  return [...unique.values()].sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at)).slice(-HISTORY_WINDOW);
}

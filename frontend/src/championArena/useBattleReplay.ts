import { useEffect, useMemo, useState } from "react";
import type { RefObject } from "react";
import { api } from "../api";
import type { BattleReplayTimeline, ChallengerChampionEvent } from "../types";
import type { ArenaView } from "./model";
import { replayFrame, validateReplay } from "./replay";

export function useBattleReplay(base: ArenaView | null, cohort: string, visible: boolean, reduced: boolean, region: RefObject<HTMLDivElement | null>) {
  const eventJson = JSON.stringify(base?.mode === "recap" && base.event?.kind !== "first_champion" ? base.event : null);
  const event = useMemo(() => JSON.parse(eventJson) as ChallengerChampionEvent | null, [eventJson]);
  const key = event ? JSON.stringify([cohort, event.event_id]) : "";
  const [loaded, setLoaded] = useState<{ key: string; timeline: BattleReplayTimeline | null; failed: boolean } | null>(null);
  const [playback, setPlayback] = useState({ key: "", index: 0, playing: false });
  const [previousContext, setPreviousContext] = useState({ key, reduced });
  if (previousContext.key !== key || previousContext.reduced !== reduced) {
    setPreviousContext({ key, reduced });
    setPlayback(previousContext.key !== key ? { key: "", index: 0, playing: false } : { ...playback, playing: false });
  }
  const [onscreen, setOnscreen] = useState(true);
  const timeline = loaded?.key === key ? loaded.timeline : null;
  const index = timeline ? playback.key === key ? playback.index : timeline.points.length - 1 : 0;
  const playing = Boolean(timeline && playback.key === key && playback.playing && !reduced);
  useEffect(() => {
    if (!event || !cohort) return;
    const controller = new AbortController();
    void api.championReplay(event.event_id, cohort, controller.signal).then(response => {
      if (!controller.signal.aborted) setLoaded({ key, timeline: validateReplay(response, event, cohort), failed: false });
    }).catch(() => { if (!controller.signal.aborted) setLoaded({ key, timeline: null, failed: true }); });
    return () => controller.abort();
  }, [key, event, cohort]);
  useEffect(() => {
    if (!timeline || !region.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setOnscreen(entry?.isIntersecting ?? false));
    observer.observe(region.current);
    return () => observer.disconnect();
  }, [timeline, region]);
  useEffect(() => {
    if (!timeline || !playing || !visible || !onscreen) return;
    const timer = window.setTimeout(() => setPlayback(current => {
      if (current.key !== key || !current.playing) return current;
      const next = Math.min(timeline.points.length - 1, current.index + 1);
      return { key, index: next, playing: next < timeline.points.length - 1 };
    }), 2000);
    return () => clearTimeout(timer);
  }, [timeline, playing, visible, onscreen, index, key]);
  const seek = (next: number) => { if (timeline) setPlayback({ key, index: Math.max(0, Math.min(timeline.points.length - 1, next)), playing: false }); };
  const play = () => { if (timeline) setPlayback({ key, index: index === timeline.points.length - 1 ? 0 : index, playing: true }); };
  const pause = () => setPlayback({ key, index, playing: false });
  const view = base && timeline ? replayFrame(base, timeline, index) : base;
  const note = !key ? "" : loaded?.key !== key ? "Checking for recorded checkpoints…" : loaded.failed ? "Checkpoint history could not be loaded. The saved final result is still available." : !timeline ? "Final result only · No playable checkpoint history was recorded for this battle." : "";
  return { view, timeline, index, playing, seek, play, pause, note };
}

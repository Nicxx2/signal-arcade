import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { ArrowRight, Clapperboard, Crown, Expand, Pause, Play, RotateCcw, ShieldCheck, Sparkles, X } from "lucide-react";
import { api } from "../api";
import type { ChallengerChampionEvent, Snapshot } from "../types";
import { SKILLS, contextFor, displaySignatures, freshness, matchingEvent, percentage, readQuality, recordedDate, resolveSelection, viewForSkill, writeQuality } from "./model";
import type { ArenaView, Fighter, Quality, Selection } from "./model";
import type { ArenaScene, SceneReport } from "./scene";
import FighterPortrait from "./FighterPortrait";
import ArenaReadout from "./ArenaReadout";
import ArenaReplay from "./ArenaReplay";
import { useBattleReplay } from "./useBattleReplay";
import { battleReadout, edgeText, position } from "./readout";
import { ATTACK_NAMES, DEFENCE_NAMES, POSE_NAMES } from "./design";
import "./arena.css";

// A failing GPU stays in compatibility mode across skill switches and modal reopenings.
let sessionGraphicsError: string | null = null;
let sessionRetriesRemaining = 1;
type MotionCommand = { key: string; kind: "replay" | "finish" } | null;

function FighterLabel({ fighter, side, champion, signature }: { fighter: Fighter | null; side: string; champion: boolean; signature: string }) {
  return <div className={`ca-name ca-name-${side}`} style={{ "--accent": fighter?.color ?? "#96a5b9" } as CSSProperties}>
    <span>{champion ? <><Crown size={12} /> Saved Champion</> : "Contender"}</span>
    <strong>{fighter?.name ?? "Identity unavailable"}</strong>
    <em title={fighter?.id}>{signature}</em>
    <small>{fighter?.family ?? "Family unknown"} <b>·</b> {fighter?.influence ?? "Unknown"}</small>
  </div>;
}

function ArenaStage({ view, quality, setQuality, reduced, active, visible, command, evidenceStale }: { view: ArenaView; quality: Quality; setQuality: (quality: Quality) => void; reduced: boolean; active: boolean; visible: boolean; command: MotionCommand; evidenceStale: boolean }) {
  const stage = useRef<HTMLDivElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const engine = useRef<ArenaScene | null>(null);
  const [onscreen, setOnscreen] = useState(() => typeof IntersectionObserver === "undefined");
  const displayed = visible && onscreen;
  const moving = active && displayed;
  const latest = useRef({ view, active: moving, quality, displayed, command });
  const syncLoading = useRef<(() => void) | null>(null);
  const [report, setReport] = useState<SceneReport | null>(null);
  const [issue, setIssue] = useState<string | null>(sessionGraphicsError);
  const [retry, setRetry] = useState(0);
  // Incomplete historical identities must not assign a ceremony to the wrong fighter.
  const completeIdentities = Boolean(view.left && (view.mode !== "recap" || view.outcome === "first_champion" || view.right));
  const enable3d = quality !== "off" && !reduced && !issue && completeIdentities;
  // A new renderer must become ready independently, including Off → Auto and motion changes.
  const [previousEnabled, setPreviousEnabled] = useState(enable3d);
  if (previousEnabled !== enable3d) { setPreviousEnabled(enable3d); setReport(null); }
  useEffect(() => {
    const observer = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(([entry]) => setOnscreen(entry?.isIntersecting ?? false));
    if (stage.current) observer?.observe(stage.current);
    return () => observer?.disconnect();
  }, []);
  useLayoutEffect(() => {
    latest.current = { view, active: moving, quality, displayed, command };
    engine.current?.setActive(enable3d && moving);
    // Replace a visible pair before paint; never draw hidden/offscreen updates.
    if (enable3d && displayed) {
      engine.current?.setView(view);
      engine.current?.setQuality(quality);
    }
    syncLoading.current?.();
  }, [view, moving, quality, displayed, command, enable3d]);
  useEffect(() => { if (command) engine.current?.[command.kind](); }, [command]);
  useEffect(() => {
    if (!enable3d || !container.current) return;
    let cancelled = false;
    let mounted: ArenaScene | null = null;
    let factory: typeof import("./scene")["createArenaScene"] | null = null;
    let importing = false;
    let frame = 0, timeout = 0, remaining = 8_000, started = 0;
    const host = container.current;
    const pauseTimeout = () => {
      if (timeout) { clearTimeout(timeout); timeout = 0; remaining = Math.max(0, remaining - (performance.now() - started)); }
    };
    const fail = (message: string) => { pauseTimeout(); sessionGraphicsError = message; setIssue(message); };
    const mountScene = () => {
      if (cancelled || !latest.current.displayed || !factory) return;
      mounted = factory(host, latest.current.view, latest.current.quality, (next) => {
        if (!cancelled) { sessionGraphicsError = null; setReport(next); }
      }, (message) => { if (!cancelled) fail(message); });
      engine.current = mounted;
      if (latest.current.command) mounted[latest.current.command.kind]();
      mounted.setActive(latest.current.active);
      pauseTimeout();
    };
    const sync = () => {
      if (cancelled || mounted) return;
      if (!latest.current.displayed) { cancelAnimationFrame(frame); frame = 0; pauseTimeout(); return; }
      // Only visible loading time counts; background tabs suspend animation frames.
      if (!timeout) {
        started = performance.now();
        timeout = window.setTimeout(() => {
          cancelled = true;
          cancelAnimationFrame(frame);
          fail("3D took too long to open. The complete 2D view is ready.");
        }, remaining);
      }
      if (frame || importing) return;
      // Let the accessible HTML shell paint before the optional renderer starts.
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (cancelled || !latest.current.displayed) return;
        if (factory) { try { mountScene(); } catch { fail("3D is unavailable on this browser. You can continue in 2D."); } return; }
        importing = true;
        void import("./scene").then(({ createArenaScene }) => {
          importing = false; factory = createArenaScene; mountScene();
        }).catch(() => { if (!cancelled) fail("3D is unavailable on this browser. You can continue in 2D."); });
      });
    };
    syncLoading.current = sync;
    sync();
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
      if (syncLoading.current === sync) syncLoading.current = null;
      mounted?.dispose();
      if (engine.current === mounted) engine.current = null;
    };
  }, [enable3d, retry]);
  const show3d = enable3d && report?.viewKey === view.key;
  const preparing3d = enable3d && !show3d;
  const signatures = displaySignatures(view.left, view.right);
  const comparison = battleReadout(view, evidenceStale);
  const measured = comparison.plot;
  return <div ref={stage} className="ca-stage" data-replay-step={view.replayStep} data-replay-final={view.replayFinal} data-renderer={show3d ? "3d" : preparing3d ? "loading" : "2d"} data-draw-calls={show3d ? report.calls : undefined} data-triangles={show3d ? report.triangles : undefined} data-geometries={show3d ? report.geometries : undefined} data-textures={show3d ? report.textures : undefined}>
    <div className="ca-stage-grid" />
    {!enable3d && <div className="ca-fallback" aria-hidden="true">
      <div className="ca-stage-orbit" />
      {view.left && <div className="ca-figure ca-figure-left"><FighterPortrait fighter={view.left} full /></div>}
      {view.right && <div className="ca-figure ca-figure-right"><FighterPortrait fighter={view.right} full /></div>}
      {!view.right && <div className="ca-solitary-emblem"><ShieldCheck /><span>{view.mode === "training" ? "PROOF BEFORE POWER" : "EARNED THROUGH EVIDENCE"}</span></div>}
    </div>}
    <div ref={container} className="ca-webgl" style={{ visibility: show3d ? "visible" : "hidden" }} aria-hidden="true" />
    {preparing3d && <div className="ca-stage-loading" role="status"><span aria-hidden="true" /><small>Opening 3D arena</small></div>}
    <div className="ca-fighters"><FighterLabel fighter={view.left} side="left" champion={view.leftIsChampion} signature={signatures[0]} />{view.right && <FighterLabel fighter={view.right} side="right" champion={false} signature={signatures[1]} />}</div>
    {view.right && (view.mode === "battle" || view.mode === "recap") && <div className="ca-stage-balance" aria-hidden="true"><div><span>Champion</span><strong>{comparison.shortTitle}</strong><span>Contender</span></div><div className="ca-stage-balance-track"><i />{comparison.band && <em style={{ left: `${position(view.lower!)}%`, width: `${position(view.upper!) - position(view.lower!)}%` }} />}{measured && <b style={{ left: `${position(view.mean!)}%` }} />}</div><small>{comparison.evidenceText}{measured ? ` · ${edgeText(view.mean)}` : ""}</small></div>}
    <div className="ca-stage-meta"><span><i /> {show3d ? `${report.tier} graphics` : reduced ? "Reduced motion · 2D" : quality === "off" ? "Graphics off · 2D" : issue ? "Compatibility · 2D" : !completeIdentities ? "Identity incomplete · 2D" : "Preparing 3D"}</span><span>{!moving ? "Animation paused" : view.replayFinal === false ? "Recorded evidence · Illustrated moves" : view.mode === "recap" ? "Illustrated result" : "Evidence decides"}</span></div>
    {issue && quality !== "off" && <div className="ca-render-notice" role="status"><span>{issue}</span><button onClick={() => setQuality("off")}>Use 2D</button>{sessionRetriesRemaining > 0 && <button onClick={() => { sessionRetriesRemaining--; setReport(null); setIssue(null); setRetry(retry + 1); }}>Retry 3D</button>}</div>}
  </div>;
}

export default function ArenaDialog({ snapshot, selection, onClose, onSelect }: { snapshot: Snapshot; selection: Selection; onClose: () => void; onSelect: (selection: Selection) => void }) {
  const dialog = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [quality, setGraphics] = useState<Quality>(readQuality);
  const [reduced, setReduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(!document.hidden);
  const [command, setCommand] = useState<MotionCommand>(null);
  const [expiredSnapshot, setExpiredSnapshot] = useState<Snapshot | null>(null);
  const [historyResult, setHistoryResult] = useState<{ key: string; events: ChallengerChampionEvent[]; note: string } | null>(null);
  const extraEvents = historyResult?.key === selection.initial.key ? historyResult.events : [];
  const historyNote = historyResult?.key === selection.initial.key ? historyResult.note : "";
  const replayRegion = useRef<HTMLDivElement>(null);
  // Retain only the most recently displayed profile, never an unbounded history. If a
  // generation changes, its proof and timestamp must not jump back to modal-open time.
  const [profileEvidence, setProfileEvidence] = useState({ snapshot, selection, view: selection.initial });
  const selectedProfile = profileEvidence.selection === selection ? profileEvidence.view : selection.initial;
  const resolvedView = resolveSelection(snapshot, { ...selection, initial: selectedProfile }, extraEvents);
  if (profileEvidence.snapshot !== snapshot || profileEvidence.selection !== selection) {
    const currentProfile = resolvedView && !resolvedView.superseded && (resolvedView.mode === "training" || resolvedView.mode === "champion");
    setProfileEvidence({ snapshot, selection, view: currentProfile ? resolvedView : selectedProfile });
  }
  const replay = useBattleReplay(resolvedView, snapshot.learning.champion_journey_cohort_key ?? "", visible, reduced, replayRegion);
  const view = replay.view;
  const missingResult = view?.mode === "interrupted" && selection.initial.mode === "battle";
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    // Freeze a newly resolved live result before it leaves the rolling snapshot window.
    if (resolvedView?.event && selection.initial.mode !== "recap") onSelect({ context: selection.context, initial: resolvedView });
  }, [resolvedView, selection, onSelect]);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current(); }
      if (event.key !== "Tab") return;
      const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]),select:not([disabled]),input:not([disabled]),summary,a[href],[tabindex="0"]') ?? []).filter((node) => !node.hidden);
      const first = nodes[0], last = nodes.at(-1);
      if (!dialog.current?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first)?.focus(); }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = oldOverflow; window.removeEventListener("keydown", keydown); if (trigger?.isConnected) trigger.focus(); };
  }, []);
  useEffect(() => {
    const initialAge = freshness(snapshot, 0);
    if (initialAge === null || initialAge > 15) return;
    const timer = window.setTimeout(() => setExpiredSnapshot(snapshot), (15 - initialAge) * 1000 + 20);
    return () => clearTimeout(timer);
  }, [snapshot]);
  useEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(preference?.matches ?? false);
    const visibility = () => setVisible(!document.hidden);
    preference?.addEventListener("change", change);
    document.addEventListener("visibilitychange", visibility);
    return () => { preference?.removeEventListener("change", change); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  useEffect(() => {
    if (!missingResult) return;
    const controller = new AbortController();
    void (async () => {
      let cursor: string | undefined;
      for (let pageNumber = 0; pageNumber < 2; pageNumber++) {
        const page = await api.championJourney(cursor, controller.signal, 50);
        if (controller.signal.aborted) return;
        const found = matchingEvent(selection.initial, page.events);
        if (found) { setHistoryResult({ key: selection.initial.key, events: [found], note: "" }); return; }
        if (!page.next_cursor) break;
        cursor = page.next_cursor;
      }
      if (!controller.signal.aborted) setHistoryResult({ key: selection.initial.key, events: [], note: "Result not loaded. Older records remain available in Champion Journey." });
    })().catch(() => { if (!controller.signal.aborted) setHistoryResult({ key: selection.initial.key, events: [], note: "Saved results could not be loaded. Try Champion Journey when the connection is available." }); });
    return () => controller.abort();
  }, [missingResult, selection]);
  const setQuality = (next: Quality) => { setGraphics(next); writeQuality(next); };
  if (!view) return null;
  const immediateAge = freshness(snapshot, 0);
  const stale = expiredSnapshot === snapshot || immediateAge === null || immediateAge > 15;
  const historical = view.mode === "recap";
  const animationActive = !paused && !reduced && visible && (historical || (!stale && !view.paused));
  const status = historical ? view.replayFinal === false ? "Recorded checkpoint" : "Saved result" : view.superseded ? "Saved profile" : view.mode === "interrupted" ? "Comparison changed" : view.paused ? "Learning paused" : view.mode === "battle" ? "Live comparison" : "Fighter profile";
  const evidenceTime = recordedDate(view.evidenceAt);
  const battle = historical ? view.outcome !== "first_champion" : view.mode === "battle" || view.mode === "interrupted";
  return <div className="ca-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="ca-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="ca-title" aria-describedby="ca-description" tabIndex={-1}>
      <header className="ca-header"><div className="ca-brand"><Sparkles size={19} /><span>CHAMPION ARENA<small>{snapshot.risk_mode === "safe" ? "Safer" : snapshot.risk_mode === "balanced" ? "Balanced" : "Aggressive"} · {SKILLS[view.skill]} · {snapshot.demo_mode ? "Demo" : "Mainnet data"}</small></span></div><button ref={closeButton} className="ca-close" onClick={onClose} aria-label="Close Champion Arena"><X size={21} /></button></header>
      <div className="ca-scroll">
        <div className="ca-intro"><span role="status" className={`ca-status ${historical ? "recorded" : !stale && !view.paused && view.mode !== "interrupted" ? "current" : ""}`}><i />{status}</span><h2 id="ca-title">{view.title}<span>.</span></h2><p id="ca-description">{view.detail}</p></div>
        <div className="ca-tabs" aria-label="Arena skill"><div>{(Object.keys(SKILLS) as Array<keyof typeof SKILLS>).map((skill) => { const next = viewForSkill(snapshot, skill); return <button key={skill} aria-pressed={!historical && view.skill === skill} disabled={!next} onClick={() => { if (next) onSelect({ context: contextFor(snapshot), initial: next }); }}>{SKILLS[skill]}</button>; })}</div>{historical && <span>{view.outcome === "first_champion" ? <Crown size={14} /> : <Clapperboard size={14} />}{view.outcome === "first_champion" ? "Champion coronation" : replay.timeline ? "Recorded comparison" : "Animated result recap"}</span>}</div>
        <div ref={replayRegion}>
        <ArenaStage view={view} quality={quality} setQuality={setQuality} reduced={reduced} active={animationActive} visible={visible} evidenceStale={!historical && stale} command={command?.key === view.key ? command : null} />
        <div className="ca-toolbar"><div><label>Graphics <select value={quality} onChange={(event) => setQuality(event.target.value as Quality)} aria-label="Battle graphics"><option value="auto">Auto · adaptive</option><option value="low">Low · compatibility</option><option value="medium">Medium</option><option value="high">High</option><option value="off">Off · 2D</option></select></label>{quality !== "off" && <button onClick={() => setQuality("off")}><Expand size={14} /> Use 2D</button>}</div>{!replay.timeline && <div><button disabled={reduced || quality === "off"} onClick={() => setPaused(!paused)}>{paused ? <Play size={14} /> : <Pause size={14} />}{paused ? "Resume" : "Pause"}</button><button disabled={reduced || quality === "off"} onClick={() => { setPaused(false); setCommand({ key: view.key, kind: "replay" }); }}><RotateCcw size={14} />{view.outcome === "first_champion" ? "Replay coronation" : historical ? "Replay recap" : "Show pose"}</button>{historical && <button onClick={() => { setPaused(true); setCommand({ key: view.key, kind: "finish" }); }}>Skip animation</button>}</div>}</div>
        <ArenaReplay replay={replay} view={view} reduced={reduced} onMotion={moving => setPaused(!moving)} />
        {!historical && <div className="ca-update-note" data-delayed={stale && !view.superseded} aria-live="off"><span>{Number.isFinite(Date.parse(view.evidenceAt ?? "")) ? `Evidence as of ${evidenceTime}` : "Evidence timestamp unavailable"}</span><span>{view.superseded || view.mode === "interrupted" ? "Selected version · saved evidence" : view.paused ? "Evidence updates paused" : stale ? "Update delayed · showing last evidence; live moves paused" : "Updates automatically"}</span></div>}
        <ArenaReadout view={view} stale={historical ? false : stale} />
        </div>
        {battle && <details className="ca-comparison-details"><summary>Comparison numbers <ArrowRight size={14} /></summary><div className="ca-metrics"><div><small>Shared outcomes</small><strong>{view.usable ?? "—"}<span>{view.observed === null ? "" : ` / ${view.observed}`}</span></strong><p>{historical ? "Usable / observed" : `Minimum ${view.minimum} usable; other guards still apply`}</p></div><div><small>Outcome coverage</small><strong>{percentage(view.coverage)}</strong><p>{historical ? view.replayFinal === false ? "At this recorded checkpoint" : "At the recorded decision" : `Required ${percentage(view.minimumCoverage)}`}</p></div><div><small>Contender average edge</small><strong>{edgeText(view.mean)}</strong><p>Difference in modeled value. Positive favors the contender; negative favors the Champion. pp = percentage points.</p></div><div><small>Conservative estimate</small><strong>{edgeText(view.lower)}</strong><p>{view.upper !== null ? `Uncertainty range ends at ${edgeText(view.upper)}. The lower end must be above zero for replacement; other checks apply.` : "Lower end of the estimate. A positive value alone cannot establish a replacement."}</p></div></div></details>}
        {historyNote && <div className="ca-evidence-note" role="status"><ShieldCheck size={17} /><p>{historyNote}</p></div>}
        <details className="ca-identities"><summary>Fighter identities & proof context <ArrowRight size={14} /></summary>{[view.left, view.right].filter((fighter): fighter is Fighter => fighter !== null).map((fighter) => <div key={fighter.id}><FighterPortrait fighter={fighter} /><p><strong>{fighter.name} · {fighter.signature}</strong><span>{fighter.id}</span><small>{fighter.family} · {fighter.influence} · Arc-forged v1 · Details v1</small><small>Signature style: {ATTACK_NAMES[fighter.details.attack]} · {DEFENCE_NAMES[fighter.details.defence]} · {POSE_NAMES[fighter.details.pose]}</small></p></div>)}<p className="ca-style-note">Each model version keeps its character across refreshes, graphics settings and replays. New generations may reuse a name but have a different signature; the full model version above identifies the fighter.</p><p className="ca-style-note">Chest symbols identify the family: three bars for Linear, a branching mark for XGBoost, and a shield outline for deterministic policies. XGBoost also has branched antennae. Armor, handheld shields and move styles are cosmetic variations, not model strength. Recorded evidence determines the comparison.</p></details>
        <footer className="ca-footer"><ShieldCheck size={14} /> Evidence earns the crown. A crown is not a profit guarantee.</footer>
      </div>
    </section>
  </div>;
}

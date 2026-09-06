import { Component, createContext, lazy, Suspense, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ArrowUpRight, Clapperboard, Crown, Swords, X } from "lucide-react";
import type { ChallengerChampionEvent, Snapshot } from "../types";
import { SKILLS, contextFor, viewForEvent, viewForSkill } from "./model";
import type { Selection, Skill } from "./model";
import FighterPortrait from "./FighterPortrait";
import "./entry.css";

const ArenaDialog = lazy(() => import("./ArenaDialog"));
const ArenaContext = createContext<{ snapshot: Snapshot; open: (selection: Selection) => void } | null>(null);
function LoadingShell({ failed = false, close }: { failed?: boolean; close: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(close);
  useEffect(() => { closeRef.current = close; }, [close]);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    button.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeRef.current(); }
      if (event.key === "Tab") { event.preventDefault(); button.current?.focus(); }
    };
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("keydown", key); document.body.style.overflow = overflow; if (trigger?.isConnected) trigger.focus(); };
  }, []);
  return <div className="ca-loading-backdrop"><section className="ca-loading-shell" role="dialog" aria-modal="true" aria-label="Champion Arena">
    <strong>{failed ? "The arena could not load." : "Opening Champion Arena…"}</strong>
    <p role="status">{failed ? "Your learning and trading continue normally. Close this view and reload the page to retry." : "Preparing your spectator view."}</p>
    <button ref={button} className="button" onClick={close}><X size={16} /> Close arena</button>
  </section></div>;
}
class ArenaBoundary extends Component<{ children: ReactNode; close: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <LoadingShell failed close={this.props.close} /> : this.props.children;
  }
}
export function ArenaProvider({ snapshot, children }: { snapshot: Snapshot; children: ReactNode }) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const close = () => setSelection(null);
  return <ArenaContext.Provider value={{ snapshot, open: setSelection }}>
    {children}
    {selection && <ArenaBoundary close={close}><Suspense fallback={<LoadingShell close={close} />}><ArenaDialog snapshot={snapshot} selection={selection} onClose={close} onSelect={setSelection} /></Suspense></ArenaBoundary>}
  </ArenaContext.Provider>;
}
export function ArenaSkillButton({ skill }: { skill: Skill }) {
  const context = useContext(ArenaContext);
  if (!context) return null;
  const view = viewForSkill(context.snapshot, skill);
  if (!view?.left) return null;
  const action = view.mode === "battle" ? "Watch battle" : view.mode === "champion" ? "View Champion" : view.mode === "interrupted" ? "View status" : "Meet contender";
  return <button className="ca-skill-launch" aria-label={`${SKILLS[skill]}: ${action} in Champion Arena`} onClick={() => context.open({ context: contextFor(context.snapshot), initial: view })}>
    <FighterPortrait fighter={view.left} />
    <span><small>Champion Arena</small><strong>{view.mode === "battle" && <Swords size={14} />}{action}</strong><em className="ca-launch-identity" title={view.left.id}>{view.left.name} · {view.left.signature}</em></span><ArrowUpRight size={16} />
  </button>;
}
export function ArenaRecapButton({ event }: { event: ChallengerChampionEvent }) {
  const context = useContext(ArenaContext);
  if (!context) return null;
  const firstChampion = event.kind === "first_champion";
  return <button className="ca-recap-launch" onClick={() => context.open({ context: contextFor(context.snapshot), initial: viewForEvent(context.snapshot, event) })}>{firstChampion ? <Crown size={13} /> : <Clapperboard size={13} />}{firstChampion ? "View coronation" : "Animated recap"}</button>;
}

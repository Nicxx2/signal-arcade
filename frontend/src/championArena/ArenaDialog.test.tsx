import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { api } from "../api";
import ArenaDialog from "./ArenaDialog";
import { createArenaScene } from "./scene";
import { contextFor, GRAPHICS_KEY, viewForEvent, viewForSkill } from "./model";
import { eventFixture, snapshotFixture } from "./fixtures";
import type { ArenaView, Selection } from "./model";

vi.mock("./scene", () => ({ createArenaScene: vi.fn() }));
vi.mock("../api", () => ({ api: { championJourney: vi.fn(), championReplay: vi.fn() } }));
const create = vi.mocked(createArenaScene);
const history = vi.mocked(api.championJourney);
let instances: Array<{ setView: ReturnType<typeof vi.fn>; setActive: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn>; replay: ReturnType<typeof vi.fn>; finish: ReturnType<typeof vi.fn>; fail: (message: string) => void }>;
let media: MediaQueryList;
let mediaChange: () => void;
let intersection: { target: Element; change: (visible: boolean) => void; disconnect: ReturnType<typeof vi.fn> };
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks(); vi.mocked(api.championReplay).mockResolvedValue({ event_id: "", cohort_key: "", timeline: null }); localStorage.clear(); localStorage.setItem(GRAPHICS_KEY, "low"); instances = [];
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
  media = { matches: false, addEventListener: (_: string, change: () => void) => { mediaChange = change; }, removeEventListener: vi.fn() } as unknown as MediaQueryList;
  vi.stubGlobal("matchMedia", () => media);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 16));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  vi.stubGlobal("IntersectionObserver", class {
    constructor(private callback: IntersectionObserverCallback) {}
    disconnect = vi.fn();
    observe(target: Element) {
      intersection = { target, change: (visible) => this.callback([{ target, isIntersecting: visible } as IntersectionObserverEntry], this as unknown as IntersectionObserver), disconnect: this.disconnect };
      intersection.change(true);
    }
  });
  create.mockImplementation((host, _view, _quality, report, fail) => {
    const canvas = document.createElement("canvas"); canvas.dataset.championRenderer = "true"; host.append(canvas);
    const emit = (view: ArenaView) => report({ viewKey: view.key, tier: "low", calls: 60, triangles: 4500, geometries: 25, textures: 0 });
    let key = _view.key;
    const instance = { setActive: vi.fn(), setView: vi.fn((view: ArenaView) => { if (view.key !== key) { key = view.key; emit(view); } }), setQuality: vi.fn(), replay: vi.fn(), finish: vi.fn(), dispose: vi.fn(() => canvas.remove()), fail };
    instances.push(instance); emit(_view); return instance;
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const frames = async (ms = 20) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); await vi.dynamicImportSettled(); }); };
function mount(selection?: Selection) {
  const snapshot = snapshotFixture();
  const props = { snapshot, selection: selection ?? { context: contextFor(snapshot), initial: viewForSkill(snapshot, "entry")! }, onClose: vi.fn(), onSelect: vi.fn() };
  return { ...render(<ArenaDialog {...props} />), props };
}

describe("arena lifecycle and complete fallback", () => {
  test("Graphics Off keeps evidence and creates no renderer or history requests", async () => {
    localStorage.setItem(GRAPHICS_KEY, "off"); mount(); await frames();
    expect(screen.getByText("87.5%")).toBeInTheDocument(); expect(screen.getAllByText("+2.4 pp").length).toBeGreaterThan(0);
    expect(create).not.toHaveBeenCalled(); expect(history).not.toHaveBeenCalled();
  });
  test("reduced motion starts in static 2D even with high graphics selected", async () => {
    Object.defineProperty(media, "matches", { value: true, configurable: true });
    localStorage.setItem(GRAPHICS_KEY, "high"); mount(); await frames();
    expect(screen.getByText("Reduced motion · 2D")).toBeInTheDocument(); expect(create).not.toHaveBeenCalled();
  });
  test("changing to reduced motion disposes the renderer immediately", async () => {
    mount(); await frames(); expect(create).toHaveBeenCalledTimes(1);
    Object.defineProperty(media, "matches", { value: true, configurable: true }); act(() => mediaChange());
    expect(instances[0]!.dispose).toHaveBeenCalledTimes(1); expect(document.querySelectorAll("canvas")).toHaveLength(0);
  });
  test("Off and back to Auto waits for a new ready renderer", async () => {
    mount(); await frames();
    fireEvent.change(screen.getByLabelText("Battle graphics"), { target: { value: "off" } });
    expect(instances[0]!.dispose).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("Battle graphics"), { target: { value: "auto" } });
    expect(screen.getByText("Opening 3D arena")).toBeInTheDocument();
    expect(document.querySelector('.ca-stage')).toHaveAttribute('data-renderer', 'loading');
    expect(document.querySelector('.ca-stage .ca-fallback')).toBeNull();
    await frames(); expect(create).toHaveBeenCalledTimes(2); expect(document.querySelectorAll("canvas")).toHaveLength(1);
  });
  test("hidden documents stop animation and fresh visible documents resume", async () => {
    mount(); await frames();
    Object.defineProperty(document, "hidden", { configurable: true, value: true }); fireEvent(document, new Event("visibilitychange"));
    expect(instances[0]!.setActive).toHaveBeenLastCalledWith(false);
    Object.defineProperty(document, "hidden", { configurable: true, value: false }); fireEvent(document, new Event("visibilitychange"));
    expect(instances[0]!.setActive).toHaveBeenLastCalledWith(true);
  });
  test("scrolling the stage out of view stops motion without replacing the renderer", async () => {
    const mounted = mount(); await frames();
    expect(intersection.target).toBe(document.querySelector(".ca-stage"));
    act(() => intersection.change(false));
    expect(instances[0]!.setActive).toHaveBeenLastCalledWith(false);
    act(() => intersection.change(true));
    expect(instances[0]!.setActive).toHaveBeenLastCalledWith(true);
    expect(create).toHaveBeenCalledTimes(1);
    mounted.unmount(); expect(intersection.disconnect).toHaveBeenCalledTimes(1);
  });
  test("a hidden tab does not initialise graphics or spend its loading timeout", async () => {
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    const mounted = mount(); await frames(9_000);
    expect(create).not.toHaveBeenCalled(); expect(screen.queryByText("Retry 3D")).toBeNull();
    Object.defineProperty(document, "hidden", { configurable: true, value: false }); fireEvent(document, new Event("visibilitychange"));
    await frames(); expect(create).toHaveBeenCalledTimes(1); mounted.unmount();
  });
  test("skip before lazy readiness is applied once and does not leak into a different recap", async () => {
    const snapshot = snapshotFixture(); const mounted = mount({ context: contextFor(snapshot), initial: viewForEvent(snapshot, eventFixture()) });
    fireEvent.click(screen.getByText("Skip animation"));
    await frames(); expect(instances[0]!.finish).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("Resume")); expect(instances[0]!.replay).not.toHaveBeenCalled();
    mounted.rerender(<ArenaDialog {...mounted.props} selection={{ context: contextFor(snapshot), initial: viewForEvent(snapshot, eventFixture("defended")) }} />);
    await frames(); expect(create).toHaveBeenCalledTimes(1); expect(instances[0]!.finish).toHaveBeenCalledTimes(1);
  });
  test("cached or expired snapshots pause live exchanges, then a new fresh snapshot resumes", async () => {
    const mounted = mount(); await frames(15_100);
    expect(screen.getByText(/Update delayed · showing last evidence/)).toBeInTheDocument(); expect(instances[0]!.setActive).toHaveBeenLastCalledWith(false);
    const marker = document.querySelector(".ca-balance-marker")!;
    const position = marker.getAttribute("style");
    const fighter = document.querySelector(".ca-name-left em")!.textContent;
    expect(marker).not.toBeNull();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "35 usable; minimum 30 met");
    expect(screen.queryByText("Waiting for a fresh update")).toBeNull();
    mounted.rerender(<ArenaDialog {...mounted.props} snapshot={snapshotFixture()} />);
    expect(screen.getByText("Live comparison")).toBeInTheDocument(); expect(instances[0]!.setActive).toHaveBeenLastCalledWith(true);
    expect(document.querySelector(".ca-balance-marker")).toBe(marker);
    expect(marker).toHaveAttribute("style", position);
    expect(document.querySelector(".ca-name-left em")!.textContent).toBe(fighter);
    expect(create).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Updates automatically")).toBeInTheDocument();
  });
  test("saved recaps remain usable with stale market snapshots", async () => {
    const snapshot = snapshotFixture(); const mounted = mount({ context: contextFor(snapshot), initial: viewForEvent(snapshot, eventFixture()) });
    await frames(15_100); expect(screen.getByText("Saved result")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Skip animation")); expect(instances[0]!.finish).toHaveBeenCalledTimes(1);
    mounted.unmount(); expect(instances[0]!.dispose).toHaveBeenCalledTimes(1);
  });
  test("Escape closes, focus stays trapped and returns to the trigger on unmount", async () => {
    const trigger = document.createElement("button"); document.body.append(trigger); trigger.focus();
    const mounted = mount(); await frames();
    const close = screen.getByRole("button", { name: "Close Champion Arena" }); expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true }); expect(document.activeElement?.tagName).toBe("SUMMARY");
    fireEvent.keyDown(window, { key: "Tab" }); expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" }); expect(mounted.props.onClose).toHaveBeenCalledTimes(1);
    mounted.unmount(); expect(trigger).toHaveFocus(); expect(document.body.style.overflow).toBe(""); trigger.remove();
  });
  test("Tab recovers focus when choosing 2D removes the focused graphics button", async () => {
    mount(); await frames();
    const use2d = screen.getByRole("button", { name: "Use 2D" });
    use2d.focus(); fireEvent.click(use2d);
    expect(use2d.isConnected).toBe(false);
    fireEvent.keyDown(window, { key: "Tab" });
    expect(screen.getByRole("button", { name: "Close Champion Arena" })).toHaveFocus();
  });
  test("closing before the lazy renderer starts leaves no late canvas", async () => {
    const mounted = mount(); mounted.unmount(); await frames(10_000); expect(create).not.toHaveBeenCalled();
  });
  test("3D starts with a neutral loading state, never a transient 2D fighter", async () => {
    mount();
    expect(document.querySelector('.ca-stage')).toHaveAttribute('data-renderer', 'loading');
    expect(document.querySelector('.ca-stage .ca-fallback')).toBeNull();
    expect(screen.getByText('Opening 3D arena')).toBeInTheDocument();
    await frames();
    expect(document.querySelector('.ca-stage')).toHaveAttribute('data-renderer', '3d');
    expect(screen.queryByText('Opening 3D arena')).toBeNull();
  });
  test("switching a visible pair reuses its canvas and is ready before paint", async () => {
    const snapshot = snapshotFixture();
    const mounted = mount(); await frames(); const canvas = document.querySelector('canvas');
    const next = viewForEvent(snapshot, eventFixture('first_champion'));
    mounted.rerender(<ArenaDialog {...mounted.props} selection={{ context: contextFor(snapshot), initial: next }} />);
    expect(create).toHaveBeenCalledTimes(1);
    expect(instances[0]!.dispose).not.toHaveBeenCalled();
    expect(document.querySelector('canvas')).toBe(canvas);
    expect(document.querySelector('.ca-stage')).toHaveAttribute('data-renderer', '3d');
    expect(instances[0]!.setView).toHaveBeenLastCalledWith(expect.objectContaining({ key: next.key }));
    mounted.unmount(); expect(instances[0]!.dispose).toHaveBeenCalledTimes(1);
  });
  test("a rapid selection before lazy startup builds only the latest pair", async () => {
    const snapshot = snapshotFixture(); const mounted = mount();
    const next = viewForEvent(snapshot, eventFixture('defended'));
    mounted.rerender(<ArenaDialog {...mounted.props} selection={{ context: contextFor(snapshot), initial: next }} />);
    await frames(); expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0]![1].key).toBe(next.key);
  });
  test("a hidden pair change waits for visibility and never reveals the previous canvas", async () => {
    const snapshot = snapshotFixture(); const mounted = mount(); await frames();
    Object.defineProperty(document, 'hidden', { configurable: true, value: true }); fireEvent(document, new Event('visibilitychange'));
    const next = viewForEvent(snapshot, eventFixture('defended'));
    mounted.rerender(<ArenaDialog {...mounted.props} selection={{ context: contextFor(snapshot), initial: next }} />);
    expect(document.querySelector('.ca-stage')).toHaveAttribute('data-renderer', 'loading');
    expect(document.querySelector('.ca-webgl')).toHaveStyle({ visibility: 'hidden' });
    expect(instances[0]!.setView).not.toHaveBeenLastCalledWith(expect.objectContaining({ key: next.key }));
    Object.defineProperty(document, 'hidden', { configurable: true, value: false }); fireEvent(document, new Event('visibilitychange'));
    expect(create).toHaveBeenCalledTimes(1);
    expect(document.querySelector('.ca-stage')).toHaveAttribute('data-renderer', '3d');
  });
  test("Strict Mode never leaves duplicate canvases and cleans the owned renderer", async () => {
    const snapshot = snapshotFixture(); const rendered = render(<StrictMode><ArenaDialog snapshot={snapshot} selection={{ context: contextFor(snapshot), initial: viewForSkill(snapshot, "entry")! }} onClose={vi.fn()} onSelect={vi.fn()} /></StrictMode>);
    await frames(); expect(document.querySelectorAll("canvas")).toHaveLength(1); rendered.unmount();
    expect(document.querySelectorAll("canvas")).toHaveLength(0); instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledTimes(1));
  });
});

describe("result reconciliation", () => {
  test("a replaced profile retains its latest displayed proof and timestamp, not its opening snapshot", async () => {
    const snapshot = snapshotFixture(), skill = snapshot.learning.skills![0]!;
    Object.assign(skill, { champion: null, testing_version: null, testing_candidate: null, gates: [{ id: "proof", label: "Independent proof", state: "collecting" }] });
    const props = { snapshot, selection: { context: contextFor(snapshot), initial: viewForSkill(snapshot, "entry")! }, onClose: vi.fn(), onSelect: vi.fn() };
    const mounted = render(<ArenaDialog {...props} />);
    const later = structuredClone(snapshot);
    later.snapshot_generated_at = later.server_time = "2026-09-04T12:12:00Z";
    later.learning.skills![0]!.gates[0]!.state = "passed";
    mounted.rerender(<ArenaDialog {...props} snapshot={later} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    const evidence = document.querySelector(".ca-update-note span")!.textContent;
    const original = document.querySelector(".ca-name-left em")!.textContent;
    const next = structuredClone(later);
    next.snapshot_generated_at = next.server_time = "2026-09-04T12:14:00Z";
    next.learning.skills![0]!.latest_candidate!.version = "next-version";
    next.learning.skills![0]!.gates[0]!.state = "collecting";
    mounted.rerender(<ArenaDialog {...props} snapshot={next} />);
    expect(screen.getByRole("heading", { name: "Saved candidate proof" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(document.querySelector(".ca-update-note span")!.textContent).toBe(evidence);
    expect(document.querySelector(".ca-name-left em")!.textContent).toBe(original);
    expect(history).not.toHaveBeenCalled();
  });
  function interrupted() {
    const original = snapshotFixture(), selection = { context: contextFor(original), initial: viewForSkill(original, "entry")! };
    const snapshot = snapshotFixture(); snapshot.learning.skills![0]!.testing_version = null;
    const props = { snapshot, selection, onClose: vi.fn(), onSelect: vi.fn() };
    return { props, ...render(<ArenaDialog {...props} />) };
  }
  test("a newly completed result is handed back as a frozen recap", () => {
    const original = snapshotFixture(), selection = { context: contextFor(original), initial: viewForSkill(original, "entry")! };
    const snapshot = snapshotFixture(); snapshot.learning.champion_journey = [eventFixture()]; const onSelect = vi.fn();
    render(<ArenaDialog snapshot={snapshot} selection={selection} onSelect={onSelect} onClose={vi.fn()} />);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ initial: expect.objectContaining({ mode: "recap", event: expect.objectContaining({ event_id: "saved-promoted" }) }) }));
  });
  test.each(["promoted", "defended", "first_champion"] as const)("an incomplete %s record preserves its outcome without inventing a winner identity", async (kind) => {
    const snapshot = snapshotFixture(), event = eventFixture(kind);
    event.candidate_version = ""; event.previous_champion_version = null; event.champion_version = "";
    mount({ context: contextFor(snapshot), initial: viewForEvent(snapshot, event) }); await frames();
    expect(screen.getByText("Champion identity unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Neither side established a replacement")).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });
  test("a disappearing comparison is not presented as paused learning", () => {
    history.mockResolvedValue({ events: [], total: 0, next_cursor: null }); interrupted();
    expect(screen.getByText("Comparison changed")).toBeInTheDocument();
    expect(screen.queryByText("Learning paused")).toBeNull();
  });
  test("a promoted record with a missing opponent keeps the known winner but uses 2D", async () => {
    const snapshot = snapshotFixture(), event = eventFixture(); event.previous_champion_version = null;
    mount({ context: contextFor(snapshot), initial: viewForEvent(snapshot, event) }); await frames();
    expect(screen.getByText("Identity incomplete · 2D")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Battle explanation" })).toHaveTextContent("Violet Pathfinder");
    expect(create).not.toHaveBeenCalled();
  });
  test("disappearing pairs request no more than two bounded pages", async () => {
    history.mockResolvedValue({ events: [], total: 1000, next_cursor: "older" }); interrupted(); await frames(40_000);
    expect(history).toHaveBeenCalledTimes(2); expect(history).toHaveBeenLastCalledWith("older", expect.any(AbortSignal), 50);
    expect(screen.getByText(/Result not loaded/)).toBeInTheDocument();
  });
  test("an older saved result reconciles without changing opponents", async () => {
    history.mockResolvedValue({ events: [eventFixture("defended")], total: 1, next_cursor: null }); const mounted = interrupted(); await frames();
    expect(screen.getByText("The crown stays")).toBeInTheDocument();
    expect(mounted.props.onSelect).toHaveBeenCalledWith(expect.objectContaining({ initial: expect.objectContaining({ left: expect.objectContaining({ id: "champion" }), right: expect.objectContaining({ id: "candidate" }) }) }));
  });
  test("late history after unmount is aborted and cannot select a recap", async () => {
    let finish!: (page: Awaited<ReturnType<typeof api.championJourney>>) => void;
    history.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const mounted = interrupted(); const signal = history.mock.calls[0]![1]!; mounted.unmount();
    await act(async () => finish({ events: [eventFixture()], total: 1, next_cursor: null }));
    expect(signal.aborted).toBe(true); expect(mounted.props.onSelect).not.toHaveBeenCalled(); expect(history).toHaveBeenCalledTimes(1);
  });
  test("history failures do not retry continuously or invent a result", async () => {
    history.mockRejectedValue(new Error("Offline")); interrupted(); await frames(60_000);
    expect(history).toHaveBeenCalledTimes(1); expect(screen.getByText("The comparison changed")).toBeInTheDocument();
  });
});

// Last: this deliberately exhausts the module's session-wide GPU retry budget.
test("context loss gives one explicit retry and stays in 2D across later reopenings", async () => {
  const mounted = mount(); await frames();
  act(() => instances[0]!.fail("Context lost")); expect(document.querySelectorAll("canvas")).toHaveLength(0);
  fireEvent.click(screen.getByText("Retry 3D")); await frames(); expect(create).toHaveBeenCalledTimes(2);
  act(() => instances[1]!.fail("Context lost again")); expect(screen.queryByText("Retry 3D")).toBeNull();
  mounted.unmount(); mount(); await frames(); expect(create).toHaveBeenCalledTimes(2); expect(screen.getByText("Compatibility · 2D")).toBeInTheDocument();
});

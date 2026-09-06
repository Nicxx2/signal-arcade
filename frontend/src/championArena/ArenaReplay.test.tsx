import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../api";
import type { BattleReplayResponse } from "../types";
import ArenaDialog from "./ArenaDialog";
import { contextFor, GRAPHICS_KEY, viewForEvent, viewForSkill } from "./model";
import { eventFixture, replayFixture, snapshotFixture } from "./fixtures";
import { createArenaScene } from "./scene";

vi.mock("../api", () => ({ api: { championReplay: vi.fn(), championJourney: vi.fn() } }));
vi.mock("./scene", () => ({ createArenaScene: vi.fn() }));
const request = vi.mocked(api.championReplay), create = vi.mocked(createArenaScene);
let intersect: (value: boolean) => void;
let reduced = false;
let scene: ReturnType<typeof createArenaScene>;
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks(); reduced = false;
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
  localStorage.setItem(GRAPHICS_KEY, "off");
  vi.stubGlobal("matchMedia", () => ({ matches: reduced, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 16));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  vi.stubGlobal("IntersectionObserver", class {
    constructor(private callback: IntersectionObserverCallback) {}
    disconnect = vi.fn();
    observe(target: Element) {
      const change = (value: boolean) => this.callback([{ target, isIntersecting: value } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
      if (!target.classList.contains("ca-stage")) intersect = change;
      change(true);
    }
  });
  create.mockImplementation((_host, _view, _quality, report) => {
    scene = { setView: vi.fn(), setActive: vi.fn(), dispose: vi.fn(), setQuality: vi.fn(), replay: vi.fn(), finish: vi.fn() };
    report({ viewKey: _view.key, tier: "low", calls: 54, triangles: 4212, geometries: 28, textures: 0 });
    return scene;
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const advance = async (ms = 20) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); await vi.dynamicImportSettled(); }); };
function mount(response?: BattleReplayResponse) {
  const fixture = replayFixture(), snapshot = snapshotFixture();
  request.mockResolvedValue(response ?? fixture.response);
  const props = { snapshot, selection: { context: contextFor(snapshot), initial: viewForEvent(snapshot, fixture.event) }, onClose: vi.fn(), onSelect: vi.fn() };
  return { ...render(<ArenaDialog {...props} />), props };
}

test("plays exact checkpoints in 2D, pauses, scrubs, and reaches only the recorded result", async () => {
  mount(); await advance();
  expect(request).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("heading", { name: "Champion defended the crown" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Replay comparison" }));
  expect(screen.getByRole("heading", { name: "Building the comparison" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Champion defended the crown" })).toBeNull();
  await advance(2000);
  expect(screen.getByRole("slider")).toHaveValue("1");
  expect(document.querySelector<HTMLElement>(".ca-readout .ca-balance-marker")!.style.left).toBe("80%");
  fireEvent.click(screen.getByRole("button", { name: "Pause replay" }));
  await advance(5000); expect(screen.getByRole("slider")).toHaveValue("1");
  fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });
  expect(document.querySelector<HTMLElement>(".ca-readout .ca-balance-marker")!.style.left).toBe("40%");
  fireEvent.click(screen.getByRole("button", { name: "Play checkpoints" }));
  await advance(2000);
  expect(screen.getByRole("heading", { name: "Champion defended the crown" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Replay comparison" })).toBeInTheDocument();
  await advance(10000); expect(screen.getByRole("slider")).toHaveValue("3");
  expect(request).toHaveBeenCalledTimes(1); expect(create).not.toHaveBeenCalled();
});

test("hidden tabs and offscreen playback stop advancing; unmount aborts the request", async () => {
  const mounted = mount(); await advance();
  fireEvent.click(screen.getByRole("button", { name: "Replay comparison" }));
  Object.defineProperty(document, "hidden", { configurable: true, value: true }); fireEvent(document, new Event("visibilitychange"));
  await advance(10000); expect(screen.getByRole("slider")).toHaveValue("0");
  Object.defineProperty(document, "hidden", { configurable: true, value: false }); fireEvent(document, new Event("visibilitychange"));
  act(() => intersect(false)); await advance(10000); expect(screen.getByRole("slider")).toHaveValue("0");
  act(() => intersect(true)); await advance(2000); expect(screen.getByRole("slider")).toHaveValue("1");
  const signal = request.mock.calls[0]![2]!;
  mounted.unmount(); expect(signal.aborted).toBe(true); await advance(10000);
});

test("new checkpoints reuse one renderer and send the same exact frame as the bar", async () => {
  localStorage.setItem(GRAPHICS_KEY, "low");
  const mounted = mount(); await advance();
  expect(create).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Replay comparison" })); await advance(2000);
  expect(scene.setView).toHaveBeenLastCalledWith(expect.objectContaining({ replayStep: 1, mean: .03, outcome: null }));
  fireEvent.click(screen.getByRole("button", { name: "Result" }));
  expect(scene.setView).toHaveBeenLastCalledWith(expect.objectContaining({ replayStep: 3, mean: -.035, outcome: "defended" }));
  expect(create).toHaveBeenCalledTimes(1); mounted.unmount(); expect(scene.dispose).toHaveBeenCalledTimes(1);
});

test("partial/sampled recordings are labelled and reduced motion allows manual stepping", async () => {
  const { response } = replayFixture(); response.timeline!.partial = response.timeline!.sampled = true; reduced = true;
  mount(response); await advance();
  expect(screen.getByText(/Partial recording:/)).toHaveTextContent("Selected checkpoints");
  expect(screen.getByRole("button", { name: "Replay comparison" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Previous checkpoint" }));
  expect(screen.getByRole("slider")).toHaveValue("2");
  await advance(10000); expect(screen.getByRole("slider")).toHaveValue("2");
  expect(create).not.toHaveBeenCalled();
});

test("old records and failed reads retain a usable final recap", async () => {
  const { response } = replayFixture(); response.timeline = null;
  const mounted = mount(response); await advance();
  expect(screen.getByText(/Final result only/)).toBeInTheDocument();
  expect(screen.queryByRole("slider")).toBeNull(); mounted.unmount();
  const next = mount(); request.mockRejectedValue(new Error("offline"));
  next.rerender(<ArenaDialog {...next.props} selection={{ ...next.props.selection, initial: viewForEvent(next.props.snapshot, eventFixture("promoted")) }} />);
  await advance(); expect(screen.getByText(/Checkpoint history could not be loaded/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "New Champion crowned" })).toBeInTheDocument();
});

test("a late response cannot enter another battle or a live comparison", async () => {
  const fixture = replayFixture(); let resolve!: (value: BattleReplayResponse) => void;
  const mounted = mount(); request.mockReturnValue(new Promise(done => { resolve = done; }));
  mounted.rerender(<ArenaDialog {...mounted.props} selection={{ ...mounted.props.selection, initial: viewForEvent(mounted.props.snapshot, eventFixture("promoted")) }} />);
  const pending = request.mock.calls.at(-1)![2]!;
  mounted.rerender(<ArenaDialog {...mounted.props} selection={{ ...mounted.props.selection, initial: viewForSkill(mounted.props.snapshot, "entry")! }} />);
  expect(pending.aborted).toBe(true);
  await act(async () => resolve(fixture.response)); await advance();
  expect(screen.getByText("Live comparison")).toBeInTheDocument(); expect(screen.queryByRole("slider")).toBeNull();
});

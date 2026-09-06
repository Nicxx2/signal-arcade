import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DiagnosticsHistory } from "./DiagnosticsHistory";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows the separate allowance and actual coverage without pretending to have history", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "recording", bytes: 1048576, budget_bytes: 536870912, queued: 0, dropped: 0, ranges: { minute: { rows: 0, from: null, to: null } } }) }));
  render(<DiagnosticsHistory />);
  expect(await screen.findByText("Recording in the background")).toBeInTheDocument();
  expect(screen.getByText("Separate 512 MiB allowance")).toBeInTheDocument();
  expect(screen.getByText("Waiting for the first interval")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download review history" })).toHaveAttribute("href", "/api/v1/diagnostics/export");
});

it("exposes gaps, storage pauses and stale acknowledgments", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "paused_storage", budget_bytes: 536870912, queued: 2, dropped: 3, early_evictions: 4 }) });
  vi.stubGlobal("fetch", fetcher);
  render(<DiagnosticsHistory />);
  expect(await screen.findByText("Paused to protect storage")).toBeInTheDocument();
  expect(screen.getByText(/3 skipped records · 4 intervals expired early · 2 queued/)).toBeInTheDocument();
  fetcher.mockResolvedValue({ ok: true, json: async () => ({ state: "recording", ack_age_seconds: 181, last_ack_at: 1, queued: 0, dropped: 0, budget_bytes: 536870912 }) });
  fireEvent.click(screen.getByRole("button", { name: "Refresh diagnostics status" }));
  expect(await screen.findByText("Recording delayed")).toBeInTheDocument();
});

it("shows unavailable status on a failed request and aborts when leaving Settings", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: false });
  vi.stubGlobal("fetch", fetcher);
  const view = render(<DiagnosticsHistory />);
  expect(await screen.findByText("History status unavailable")).toBeInTheDocument();
  view.unmount();
  await waitFor(() => {
    const options = fetcher.mock.calls.at(0)?.at(1) as RequestInit | undefined;
    expect(options?.signal?.aborted).toBe(true);
  });
});

it("uses the server's elapsed time when the device clock disagrees", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "recording", ack_age_seconds: 5, last_ack_at: 1, queued: 0, dropped: 0, budget_bytes: 536870912 }) }));
  render(<DiagnosticsHistory />);
  expect(await screen.findByText("Recording in the background")).toBeInTheDocument();
  expect(screen.queryByText("Recording delayed")).not.toBeInTheDocument();
});

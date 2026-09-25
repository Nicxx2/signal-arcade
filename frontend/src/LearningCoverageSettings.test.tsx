import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { LearningCoverageSettings } from "./LearningCoverageSettings";
import { api } from "./api";
import type { CoverageSettings } from "./types";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const policy: CoverageSettings = { percent: 70, revision: 0, effective_at: null, options: [70, 65, 60, 55], error: null, coach_percent: 70 };
const props = () => ({ policy, busy: false, setBusy: vi.fn(), reportIssue: vi.fn(), resolveIssue: vi.fn(), refresh: vi.fn().mockResolvedValue(undefined) });
const expand = () => fireEvent.click(screen.getByRole("button", { name: "Show" }));

test("compact by default and explicitly describes scope without changing the default", () => {
  render(<LearningCoverageSettings {...props()} />);
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.getByText("70% coverage")).toBeInTheDocument();
  expand();
  expect(screen.getByRole("combobox")).toHaveValue("70");
  expect(screen.getAllByRole("option").map(x => x.textContent)).toEqual(["70% (default)", "65%", "60%", "55%"]);
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
  expect(screen.getByText(/including for ongoing health checks/)).toBeInTheDocument();
  expect(screen.getByText(/Coach-derived support/)).toBeInTheDocument();
});

test("editing does not save; successful save uses a revision and survives a stale snapshot", async () => {
  const save = vi.spyOn(api, "setCoverage").mockResolvedValue({ ...policy, percent: 65, revision: 1 });
  const p = props();
  render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "65" } });
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith(65, 0));
  expect(await screen.findByText("65% coverage")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
  expect(p.refresh).toHaveBeenCalled();
});

test("concurrent changes cannot silently overwrite the other saved choice", () => {
  const p = props();
  const { rerender } = render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "65" } });
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, percent: 60, revision: 1 }} />);
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Use current setting" }));
  expect(screen.getByRole("combobox")).toHaveValue("60");
});

test("a failed save never displays the draft as saved", async () => {
  vi.spyOn(api, "setCoverage").mockRejectedValue(new Error("Conflict"));
  const p = props(); render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "60" } });
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  await waitFor(() => expect(p.reportIssue).toHaveBeenCalled());
  expect(screen.getByText("70% coverage")).toBeInTheDocument();
});

test("refresh failure after a successful save reports the actual outcome", async () => {
  vi.spyOn(api, "setCoverage").mockResolvedValue({ ...policy, percent: 60, revision: 1 });
  const p = props(); p.refresh.mockRejectedValue(new Error("Refresh failed"));
  render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "60" } });
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  await waitFor(() => expect(p.reportIssue).toHaveBeenCalledWith("learning", "Coverage saved; dashboard refresh failed", expect.any(Error)));
  expect(screen.getByText("60% coverage")).toBeInTheDocument();
});

test("old server stays unavailable and invalid saved configuration can be repaired", () => {
  const p = props(); const { rerender } = render(<LearningCoverageSettings {...p} policy={undefined} />); expand();
  expect(screen.getByRole("combobox")).toBeDisabled();
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, error: "Invalid saved setting" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid saved setting");
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeEnabled();
});

test("55 is explicit, revisioned and survives a stale dashboard after saving", async () => {
  const save = vi.spyOn(api, "setCoverage").mockResolvedValue({ ...policy, percent: 55, revision: 1 });
  const p = props(); const { rerender } = render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "55" } });
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith(55, 0));
  expect(await screen.findByText("55% coverage")).toBeInTheDocument();
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy }} />);
  expect(screen.getByRole("combobox")).toHaveValue("55");
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
});

test("an older server does not advertise 55 and duplicate or unsupported options are ignored", () => {
  const p = props(); const { rerender } = render(<LearningCoverageSettings {...p} policy={{ ...policy, options: [70, 65, 60] }} />); expand();
  expect(screen.queryByRole("option", { name: "55%" })).toBeNull();
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, options: [55, 20, 70, 55, 60, 56, 65, NaN] }} />);
  expect(screen.getAllByRole("option").map(x => x.textContent)).toEqual(["70% (default)", "65%", "60%", "55%"]);
});

test.each([[], undefined, "70,65,60,55"])("missing or malformed capabilities do not enable saving: %s", options => {
  render(<LearningCoverageSettings {...props()} policy={{ ...policy, error: "Invalid saved setting", options: options as unknown as number[] }} />); expand();
  expect(screen.getByRole("combobox")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
});

test("capability removal blocks a draft without silently changing its value", () => {
  const save = vi.spyOn(api, "setCoverage");
  const p = props(); const { rerender } = render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "55" } });
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, options: [70, 65, 60] }} />);
  expect(screen.getByRole("combobox")).toHaveValue("55");
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
  expect(save).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "60" } });
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeEnabled();
});

test("new server capabilities take precedence over the cached successful-save response", async () => {
  vi.spyOn(api, "setCoverage").mockResolvedValue({ ...policy, percent: 55, revision: 1 });
  const p = props(); const { rerender } = render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "55" } });
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  expect(await screen.findByText("55% coverage")).toBeInTheDocument();
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, options: [70, 65, 60] }} />);
  expect(screen.getByRole("option", { name: "55% (unavailable)" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, options: undefined as unknown as number[] }} />);
  expect(screen.getByRole("combobox")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeDisabled();
});

test("restoring capabilities preserves the unsaved 55 draft and still needs an explicit save", async () => {
  const save = vi.spyOn(api, "setCoverage").mockResolvedValue({ ...policy, percent: 55, revision: 1 });
  const p = props(); const { rerender } = render(<LearningCoverageSettings {...p} />); expand();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "55" } });
  rerender(<LearningCoverageSettings {...p} policy={{ ...policy, options: [] }} />);
  expect(screen.getByRole("combobox")).toHaveValue("55");
  expect(screen.getByRole("combobox")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  expect(save).not.toHaveBeenCalled();
  rerender(<LearningCoverageSettings {...p} />);
  expect(screen.getByRole("combobox")).toHaveValue("55");
  expect(screen.getByRole("button", { name: "Save requirement" })).toBeEnabled();
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
  await waitFor(() => expect(save).toHaveBeenCalledExactlyOnceWith(55, 0));
  expect(await screen.findByText("55% coverage")).toBeInTheDocument();
});

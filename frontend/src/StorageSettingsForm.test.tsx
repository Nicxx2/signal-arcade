import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError } from "./api";
import { StorageSettingsForm } from "./StorageSettingsForm";
import type { StorageStatus } from "./types";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const policy = { max_database_bytes: 16 * 1024**3, raw_trade_retention_hours: 24, policy_revision: 0 };
const props = () => ({ policy, refresh: vi.fn().mockResolvedValue(undefined), busy: false, setBusy: vi.fn(), reportIssue: vi.fn(), resolveIssue: vi.fn() });
const budget = () => screen.getByRole("spinbutton", { name: /Live-data budget/ });
const hours = () => screen.getByRole("spinbutton", { name: /Raw event history/ });
const edit = () => fireEvent.change(budget(), { target: { value: "30" } });
const result = { ...policy, max_database_bytes: 30 * 1024**3, policy_revision: 1 } as StorageStatus;

test("untouched fields follow server changes; dirty fields require reviewing conflicts", () => {
  const p = props(), view = render(<StorageSettingsForm {...p} />);
  view.rerender(<StorageSettingsForm {...p} policy={{ ...policy, raw_trade_retention_hours: 12, policy_revision: 1 }} />);
  expect(hours()).toHaveValue(12);
  edit();
  view.rerender(<StorageSettingsForm {...p} policy={{ ...policy, raw_trade_retention_hours: 6, policy_revision: 2 }} />);
  expect(budget()).toHaveValue(30); expect(hours()).toHaveValue(12);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Use current settings" }));
  expect(hours()).toHaveValue(6); expect(budget()).toHaveValue(16);
});

test("save is guarded, acknowledges before refresh, and resists stale snapshots", async () => {
  const save = vi.spyOn(api, "updateStorageSettings").mockResolvedValue(result);
  const p = props(); p.refresh.mockImplementation(() => new Promise(() => {}));
  const view = render(<StorageSettingsForm {...p} />); edit();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Saved" })).toBeDisabled();
  expect(save).toHaveBeenCalledWith(30, 24, 0);
  view.rerender(<StorageSettingsForm {...p} policy={{ ...policy }} />);
  expect(budget()).toHaveValue(30);
  view.rerender(<StorageSettingsForm {...p} policy={{ ...policy, max_database_bytes: 20 * 1024**3, policy_revision: 2 }} />);
  expect(budget()).toHaveValue(20);
  expect(screen.queryByText(/Policy saved/)).toBeNull();
});

test("duplicate submissions share one save and cannot escape the busy guard", async () => {
  let resolve!: (v: StorageStatus) => void;
  const save = vi.spyOn(api, "updateStorageSettings").mockImplementation(() => new Promise(r => { resolve = r; }));
  render(<StorageSettingsForm {...props()} />); edit();
  const form = budget().closest("form")!;
  fireEvent.submit(form); fireEvent.submit(form);
  expect(save).toHaveBeenCalledTimes(1);
  resolve(result);
  await screen.findByRole("button", { name: "Saved" });
});

test("timeout preserves edits and never falsely claims no save happened", async () => {
  const save = vi.spyOn(api, "updateStorageSettings").mockRejectedValue(new Error("timeout"));
  const p = props(); render(<StorageSettingsForm {...p} />); edit();
  fireEvent.submit(budget().closest("form")!);
  expect(await screen.findByText(/The save may have completed/)).toBeInTheDocument();
  expect(budget()).toHaveValue(30);
  fireEvent.submit(budget().closest("form")!);
  expect(save).toHaveBeenCalledTimes(1);
  expect(p.reportIssue).toHaveBeenCalledWith("storage", expect.stringContaining("could not be confirmed"), expect.any(Error));
});

test("server conflict is rejected without losing edits or silently retrying", async () => {
  const save = vi.spyOn(api, "updateStorageSettings").mockRejectedValue(new ApiError("Conflict", 409));
  render(<StorageSettingsForm {...props()} />); edit(); fireEvent.submit(budget().closest("form")!);
  await screen.findByRole("alert");
  expect(budget()).toHaveValue(30); expect(save).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("failed refresh does not undo an acknowledged save", async () => {
  vi.spyOn(api, "updateStorageSettings").mockResolvedValue(result);
  const p = props(); p.refresh.mockRejectedValue(new Error("offline"));
  render(<StorageSettingsForm {...p} />); edit(); fireEvent.submit(budget().closest("form")!);
  await waitFor(() => expect(p.reportIssue).toHaveBeenCalledWith("storage", "Storage settings saved; dashboard refresh failed", expect.any(Error)));
  expect(screen.getByRole("button", { name: "Saved" })).toBeDisabled();
});

test.each([undefined, -1, NaN, 0.5])("unsupported revision %s cannot silently use an unguarded save", revision => {
  const save = vi.spyOn(api, "updateStorageSettings");
  render(<StorageSettingsForm {...props()} policy={{ ...policy, policy_revision: revision }} />);
  expect(budget()).toBeDisabled(); expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(save).not.toHaveBeenCalled();
});

test("a malformed success response remains unconfirmed", async () => {
  vi.spyOn(api, "updateStorageSettings").mockResolvedValue({ ...result, raw_trade_retention_hours: 6 });
  render(<StorageSettingsForm {...props()} />); edit(); fireEvent.submit(budget().closest("form")!);
  await screen.findByText(/The save may have completed/);
  expect(screen.queryByText(/Policy saved/)).toBeNull();
});

test("an existing fractional budget survives a retention-only edit", async () => {
  const fractional = { ...policy, max_database_bytes: Math.trunc(2.73 * 1024**3) };
  const save = vi.spyOn(api, "updateStorageSettings").mockResolvedValue({ ...fractional, raw_trade_retention_hours: 12, policy_revision: 1 } as StorageStatus);
  render(<StorageSettingsForm {...props()} policy={fractional} />);
  fireEvent.change(hours(), { target: { value: "12" } });
  expect((budget() as HTMLInputElement).validity.valid).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByRole("button", { name: "Saved" });
  expect(save).toHaveBeenCalledWith(fractional.max_database_bytes / 1024**3, 12, 0);
});

test.each([408, 500, 503])("HTTP %s preserves an uncertain save until review", async status => {
  vi.spyOn(api, "updateStorageSettings").mockRejectedValue(new ApiError("Unavailable", status));
  render(<StorageSettingsForm {...props()} />); edit(); fireEvent.submit(budget().closest("form")!);
  await screen.findByText(/The save may have completed/);
  expect(budget()).toHaveValue(30);
});

test("changed values without an advanced revision are not acknowledged", async () => {
  vi.spyOn(api, "updateStorageSettings").mockResolvedValue({ ...result, policy_revision: 0 });
  render(<StorageSettingsForm {...props()} />); edit(); fireEvent.submit(budget().closest("form")!);
  await screen.findByText(/The save may have completed/);
  expect(screen.queryByText(/Policy saved/)).toBeNull();
});

test("a delayed acknowledgement cannot replace a newer browser policy", async () => {
  let resolve!: (value: StorageStatus) => void;
  vi.spyOn(api, "updateStorageSettings").mockImplementation(() => new Promise(r => { resolve = r; }));
  const p = props(), view = render(<StorageSettingsForm {...p} />);
  edit(); fireEvent.submit(budget().closest("form")!);
  view.rerender(<StorageSettingsForm {...p} policy={{ ...policy, max_database_bytes: 20 * 1024**3, policy_revision: 2 }} />);
  resolve(result);
  await waitFor(() => expect(budget()).toHaveValue(20));
  expect(screen.queryByText(/Policy saved/)).toBeNull();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("a timed-out save can be reconciled without a second write", async () => {
  const save = vi.spyOn(api, "updateStorageSettings").mockRejectedValue(new Error("response lost"));
  const p = props(), view = render(<StorageSettingsForm {...p} />);
  edit(); fireEvent.submit(budget().closest("form")!);
  await screen.findByText(/The save may have completed/);
  view.rerender(<StorageSettingsForm {...p} policy={result} />);
  fireEvent.click(screen.getByRole("button", { name: "Use current settings" }));
  expect(budget()).toHaveValue(30);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(save).toHaveBeenCalledTimes(1);
});

test.each([
  ["budget", ""], ["budget", "0.49"], ["budget", "100.1"],
  ["history", ""], ["history", "1.5"], ["history", "721"],
])("invalid %s value %s cannot submit even without browser validation", (field, value) => {
  const save = vi.spyOn(api, "updateStorageSettings");
  const p = props(); render(<StorageSettingsForm {...p} />);
  fireEvent.change(field === "budget" ? budget() : hours(), { target: { value } });
  fireEvent.submit(budget().closest("form")!);
  expect(save).not.toHaveBeenCalled();
  expect(p.reportIssue).toHaveBeenCalledWith("storage", "Storage settings are invalid", expect.any(Error));
});

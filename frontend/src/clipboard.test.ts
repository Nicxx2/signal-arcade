import { afterEach, expect, test, vi } from "vitest";

import { copyText } from "./clipboard";

const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
const execCommandDescriptor = Object.getOwnPropertyDescriptor(document, "execCommand");

afterEach(() => {
  if (clipboardDescriptor) Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
  else Reflect.deleteProperty(navigator, "clipboard");
  if (execCommandDescriptor) Object.defineProperty(document, "execCommand", execCommandDescriptor);
  else Reflect.deleteProperty(document, "execCommand");
  vi.restoreAllMocks();
});

test("uses the standard clipboard API when available", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });

  await expect(copyText("mint-address")).resolves.toBe(true);
  expect(writeText).toHaveBeenCalledWith("mint-address");
});

test("falls back to a temporary selected field when clipboard access is denied", async () => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockRejectedValue(new Error("blocked")) },
  });
  const execCommand = vi.fn().mockReturnValue(true);
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: execCommand,
  });

  await expect(copyText("mint-address")).resolves.toBe(true);
  expect(execCommand).toHaveBeenCalledWith("copy");
  expect(document.querySelector("textarea")).not.toBeInTheDocument();
});

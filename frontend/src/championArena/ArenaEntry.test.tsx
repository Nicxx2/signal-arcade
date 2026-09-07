import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ArenaProvider, ArenaRecapButton, ArenaSkillButton } from "./ArenaEntry";
import { GRAPHICS_KEY } from "./model";
import { eventFixture, snapshotFixture, skillFixture } from "./fixtures";

afterEach(() => { cleanup(); localStorage.clear(); });
test("switching skills preserves the original trigger for focus restoration", async () => {
  localStorage.setItem(GRAPHICS_KEY, "off");
  const snapshot = snapshotFixture(); snapshot.learning.skills!.push({ ...skillFixture(), skill: "exit" });
  render(<ArenaProvider snapshot={snapshot}><ArenaSkillButton skill="entry" /></ArenaProvider>);
  const trigger = screen.getByRole("button", { name: "Entry: Watch battle in Champion Arena" });
  trigger.focus(); fireEvent.click(trigger);
  const exit = await screen.findByRole("button", { name: "Exit" });
  exit.focus(); fireEvent.click(exit);
  await waitFor(() => expect(screen.getByRole("button", { name: "Exit" })).toHaveAttribute("aria-pressed", "true"));
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(trigger).toHaveFocus(); expect(document.body.style.overflow).toBe("");
});

test.each(["first_champion", "promoted", "defended", "inconclusive"] as const)("labels the %s milestone without inventing a live battle", async (kind) => {
  localStorage.setItem(GRAPHICS_KEY, "off");
  render(<ArenaProvider snapshot={snapshotFixture()}><ArenaRecapButton event={eventFixture(kind)} /></ArenaProvider>);
  const first = kind === "first_champion";
  fireEvent.click(screen.getByRole("button", { name: first ? "View coronation" : "Animated recap" }));
  await screen.findByRole("button", { name: "Close Champion Arena" });
  if (first) {
    expect(screen.getByRole("heading", { name: "A Champion is born." })).toBeInTheDocument();
    expect(screen.getByText("Champion coronation")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replay coronation" })).toBeDisabled();
    expect(document.querySelectorAll(".ca-figure")).toHaveLength(1);
    expect(screen.queryByText("Shared outcomes")).not.toBeInTheDocument();
    expect(screen.queryByText("Contender")).not.toBeInTheDocument();
  } else {
    expect(screen.getByText("Animated result recap")).toBeInTheDocument();
    expect(document.querySelectorAll(".ca-figure")).toHaveLength(2);
  }
  expect(document.querySelector("canvas")).toBeNull();
});

test.each([
  ["testing", "Watch battle"], ["champion", "View Champion"], ["training", "Meet contender"],
  ["missing artifact", "View status"], ["self comparison", "View status"], ["suspended", "Watch battle"],
] as const)("the %s skill offers the correct action", async (state, action) => {
  localStorage.setItem(GRAPHICS_KEY, "off");
  const snapshot = snapshotFixture(), skill = snapshot.learning.skills![0]!;
  if (state === "champion" || state === "training") { skill.testing_version = null; skill.testing_candidate = null; }
  if (state === "training") skill.champion = null;
  if (state === "missing artifact") skill.testing_candidate = null;
  if (state === "self comparison") { skill.testing_version = skill.champion!.version; skill.testing_candidate = skill.champion; }
  if (state === "suspended") { skill.state = "suspended"; skill.active_version = null; }
  render(<ArenaProvider snapshot={snapshot}><ArenaSkillButton skill="entry" /></ArenaProvider>);
  const trigger = screen.getByRole("button", { name: `Entry: ${action} in Champion Arena` });
  if (state === "suspended") {
    fireEvent.click(trigger); await screen.findByText("Proof paused");
    expect(document.querySelector(".ca-name-left")).toHaveTextContent("Suspended");
    expect(document.querySelector("canvas")).toBeNull();
  }
});

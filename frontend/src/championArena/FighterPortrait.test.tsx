import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import FighterPortrait, { ChampionRecordPortrait } from "./FighterPortrait";
import { makeFighter } from "./model";

afterEach(cleanup);
const record = { skill: "entry" as const, champion_version: "champion", champion_codename: "Steady Sentinel", model_family: "linear" as const };

test("a reigning portrait matches the arena fighter and survives name or influence changes", () => {
  const mounted = render(<ChampionRecordPortrait record={record} />);
  const original = mounted.container.querySelector(".fighter-portrait")!.outerHTML;
  mounted.rerender(<FighterPortrait fighter={makeFighter(record.champion_version, record.champion_codename, record.model_family, record.skill, "Suspended")} />);
  expect(mounted.container.querySelector(".fighter-portrait")!.outerHTML).toBe(original);
  mounted.rerender(<ChampionRecordPortrait record={{ ...record, champion_codename: "A renamed Champion" }} />);
  expect(mounted.container.querySelector(".fighter-portrait")!.outerHTML).toBe(original);
  expect(mounted.container.querySelector("canvas")).toBeNull();
});

test.each(["", "   "])("a missing artifact ID (%j) shows a neutral badge rather than an invented fighter", (id) => {
  const mounted = render(<ChampionRecordPortrait record={{ ...record, champion_version: id }} />);
  expect(mounted.container.querySelector(".fighter-portrait")).toBeNull();
  expect(mounted.container.querySelector(".ca-reign-unknown")).toHaveAttribute("title", "Fighter identity unavailable");
});

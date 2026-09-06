import { beforeEach, expect, test, vi } from "vitest";
import { AUTO_TIER_KEY, QualityGovernor } from "./performance";

beforeEach(() => { localStorage.clear(); });

test("Auto starts Low and does not upgrade on a wall-clock wait", () => {
  const governor = new QualityGovernor("auto");
  expect(governor.tier).toBe("low");
  for (let i = 0; i < 100; i++) governor.sample(2, 33.4);
  expect(governor.tier).toBe("low");
});
test("sustained active headroom can upgrade without bouncing", () => {
  const governor = new QualityGovernor("auto");
  for (let i = 0; i < 940; i++) governor.sample(2, 33.4);
  expect(governor.tier).toBe("medium");
  for (let i = 0; i < 100; i++) governor.sample(2, 33.4);
  expect(governor.tier).toBe("medium");
});
test("High yields to repeated poor performance and respects cooldown", () => {
  const governor = new QualityGovernor("high");
  for (let i = 0; i < 110; i++) governor.sample(50, 60);
  expect(governor.tier).toBe("medium");
  for (let i = 0; i < 50; i++) governor.sample(50, 60);
  expect(governor.tier).toBe("medium");
});
test("a very slow device falls back rather than ignoring slow samples", () => {
  const governor = new QualityGovernor("low");
  const results = Array.from({ length: 30 }, () => governor.sample(400, 500));
  expect(results).toContain("fallback");
});
test("changing an explicit preference resets previous headroom", () => {
  const governor = new QualityGovernor("auto");
  for (let i = 0; i < 800; i++) governor.sample(1, 33.4);
  governor.setPreference("low");
  for (let i = 0; i < 1000; i++) governor.sample(1, 33.4);
  expect(governor.tier).toBe("low");
});

test("Auto resumes its last measured tier while explicit preferences take precedence", () => {
  const previous = new QualityGovernor('auto');
  for (let i = 0; i < 940; i++) previous.sample(2, 33.4);
  expect(new QualityGovernor('auto').tier).toBe('medium');
  expect(new QualityGovernor('low').tier).toBe('low');
  expect(new QualityGovernor('high').tier).toBe('high');
});

test("remembered Auto tiers still downgrade under load and save the safer tier", () => {
  localStorage.setItem(AUTO_TIER_KEY, 'high');
  const governor = new QualityGovernor('auto');
  for (let i = 0; i < 110; i++) governor.sample(50, 60);
  expect(governor.tier).toBe('medium');
  expect(new QualityGovernor('auto').tier).toBe('medium');
});

test("invalid or unavailable storage uses safe Low defaults", () => {
  localStorage.setItem(AUTO_TIER_KEY, 'ultra');
  expect(new QualityGovernor('auto').tier).toBe('low');
  const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
  expect(new QualityGovernor('auto').tier).toBe('low');
  spy.mockRestore();
});

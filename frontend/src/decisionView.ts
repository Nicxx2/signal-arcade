import type { Decision } from "./types";

export interface DecisionViewTiming {
  asOfMs: number;
  candidateWindowMinutes: number;
  staleMarketSeconds: number;
}

export function latestDecisionsByMint(decisions: Decision[]) {
  const ordered = [...decisions].sort(
    (left, right) => safeTimestamp(right.created_at) - safeTimestamp(left.created_at),
  );
  const latestByMint = new Map<string, Decision>();
  ordered.forEach((decision) => {
    if (!latestByMint.has(decision.mint)) latestByMint.set(decision.mint, decision);
  });
  return [...latestByMint.values()];
}

export function organizeDecisions(decisions: Decision[], timing: DecisionViewTiming) {
  const latest = latestDecisionsByMint(decisions);
  const currentIds = new Set<string>();
  const best = latest
    .filter((decision) => {
      const current =
        (decision.action === "enter" || decision.action === "watch") &&
        evidenceIsFresh(decision, timing);
      if (current) currentIds.add(decision.decision_id);
      return current;
    })
    .sort(
      (left, right) =>
        right.score.composite - left.score.composite ||
        safeTimestamp(right.created_at) - safeTimestamp(left.created_at),
    );
  const passed = latest
    .filter((decision) => {
      const current =
        (decision.action === "pass" || decision.action === "abstain") &&
        isInsideCandidateWindow(decision, timing);
      if (current) currentIds.add(decision.decision_id);
      return current;
    })
    .sort(
      (left, right) => safeTimestamp(right.created_at) - safeTimestamp(left.created_at),
    );
  // One token belongs to exactly one visible group. Older checkpoints remain durable in the
  // backend for replay/explanations, but duplicating them across groups made the live board
  // look contradictory.
  const earlier = latest.filter((decision) => !currentIds.has(decision.decision_id));
  return { best, passed, earlier };
}

function evidenceIsFresh(decision: Decision, timing: DecisionViewTiming) {
  if (!isInsideCandidateWindow(decision, timing)) return false;
  const freshness = decision.feature_snapshot.values.market_freshness?.value;
  if (typeof freshness !== "number" || !Number.isFinite(freshness) || freshness < 0) return false;
  const elapsedSeconds = Math.max(
    0,
    (timing.asOfMs - safeTimestamp(decision.created_at)) / 1_000,
  );
  return freshness + elapsedSeconds <= timing.staleMarketSeconds;
}

function isInsideCandidateWindow(decision: Decision, timing: DecisionViewTiming) {
  const createdAt = safeTimestamp(decision.created_at);
  if (!Number.isFinite(createdAt)) return false;
  const ageMs = timing.asOfMs - createdAt;
  return ageMs >= -5_000 && ageMs <= timing.candidateWindowMinutes * 60_000;
}

function safeTimestamp(value: string) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY;
}

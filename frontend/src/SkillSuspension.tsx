import type { ChallengerSkillStatus } from "./types";

export function SkillSuspension({ skill, paused, supportAllowed }: {
  skill: Pick<ChallengerSkillStatus, "state" | "suspension">; paused: boolean; supportAllowed: boolean;
}) {
  if (skill.state !== "suspended") return null;
  const proof = skill.suspension;
  const reason = proof?.reason === "degraded" ? "Recent evidence showed harm."
    : proof?.reason === "unverifiable" ? "Recent evidence could not verify safe support."
      : "Current activation proof needs a qualified replacement.";
  const since = proof?.since ? new Date(proof.since) : null;
  const checkLabels: Record<string, string> = { usable_outcomes: "usable outcomes", coverage: "coverage", advantage: "safe advantage", harm: "harm limit" };
  const failed = proof?.failed_checks?.map(key => checkLabels[key]).filter(Boolean) ?? [];
  return <details className="challenger-artifact-details">
    <summary>Support suspended · {paused ? "learning paused" : "learning continues"}</summary>
    <p>{reason} The Baseline retains this role. {since && Number.isFinite(since.getTime()) && <>Suspended {since.toLocaleString()}.</>}</p>
    {proof?.status === "collecting" || proof?.status === "waiting" || proof?.status === "passed"
      ? <p>{!supportAllowed ? "Automatic support is off. " : paused ? "Resume learning to continue checks. " : ""}
        {proof.status === "passed" ? "The recovery trial passed; current activation gates must also pass."
          : `Fresh recovery trial: ${proof.enrolled_count} / ${proof.window_size} enrolled · ${proof.observed_count} resolved · ${proof.usable_count} usable.`}
        {" "}One fixed window must pass 70% coverage, a safe advantage and harm checks before this Champion can return. Failed windows are not retried.</p>
      : <>
        {proof?.status === "failed" && <p>Recovery trial finished: {proof.usable_count} usable of {proof.observed_count} resolved.
          {" "}{failed.length ? `Checks not met: ${failed.join(", ")}.` : "Not all safety checks passed; individual results were not recorded."}
          {" "}This fixed trial will not restart.</p>}
        {proof?.status === "context_changed" && <p>The skill combination changed during recovery. This trial cannot establish support for the new combination.</p>}
        <p>A newly proved replacement can still qualify through the normal battle process.</p>
      </>}
    <p>{paused ? "Research and support remain paused." : "New candidates and shadow comparisons continue. Recovery does not award a new crown."}</p>
  </details>;
}

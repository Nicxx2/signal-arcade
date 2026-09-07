import type { EntryProofStatus, LearningStatus } from "./types";

export function supportedEntryProof(learning: LearningStatus): EntryProofStatus | null {
  const proof = learning.entry_proof;
  return proof?.version === "entry-proof-v1"
    && Array.isArray(proof.families)
    && proof.activation
    && Array.isArray(proof.activation.gates)
    ? proof : null;
}

export function entryProofSummary(learning: LearningStatus): string {
  if (!learning.collecting_from_current_source) return "Saved proof · source separate";
  const proof = supportedEntryProof(learning);
  const entryActive = proof ? proof.activation.active
    : learning.active_skill_versions?.entry || learning.active_model;
  if (learning.mode === "active" && entryActive) return "Entry influence active";
  if (learning.mode === "off") return "Learning paused";
  if (learning.activation_available) return "Ready for activation";
  return proof?.activation.champion || learning.skills?.some(s => s.skill === "entry" && s.champion)
    ? "Champion saved · activation gated" : "First Entry Champion pending";
}

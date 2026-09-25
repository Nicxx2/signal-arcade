import type { ChallengerSkillStatus } from "./types";

type Artifact = NonNullable<ChallengerSkillStatus["latest_candidate"]>;
const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString() : "Unavailable";
const timestamp = (value: unknown) => {
  if (typeof value !== "string") return null;
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i.exec(value);
  if (!parts) return null;
  const year = Number(parts[1]), month = Number(parts[2]), day = Number(parts[3]);
  const hour = Number(parts[4]), minute = Number(parts[5]), second = Number(parts[6]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 0;
  // Date.parse normalizes some impossible dates instead of rejecting them.
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days || hour > 23 || minute > 59 || second > 59) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/** Only saved generation metadata; never reconstruct a historical cohort from live rows. */
export default function LearningFitDetails({ artifact }: { artifact: Artifact }) {
  const native = artifact.schema_version === "challenger-skill-v2";
  const coach = artifact.schema_version === "challenger-skill-coach-v1";
  const discovery = native && (artifact.skill === "entry" || artifact.skill === "manipulation");
  const sizing = native && artifact.skill === "sizing";
  const exit = native && artifact.skill === "exit";
  const contextual = exit && artifact.recipe_version === "exit-context-v1";
  const start = timestamp(artifact.evidence_started_at);
  const end = timestamp(artifact.evidence_ended_at);
  const cutoff = timestamp(artifact.training_cutoff_at);
  const period = start !== null && end !== null && end >= start
    ? `${new Date(start).toLocaleString()} – ${new Date(end).toLocaleString()}` : "Unavailable";
  const rows = [
    [discovery ? "Usable Discovery outcomes" : sizing || exit ? "Policy observations" : coach ? "Forward usable outcomes" : "Recorded sample count", count(artifact.sample_count)],
    [coach ? "Historical screening outcomes" : contextual ? "Training cohort" : exit ? "Timing selection rows" : "Training rows", count(artifact.training_count)],
    ...(!coach ? [["Validation rows", count(artifact.validation_count)]] : []),
    ...(!coach ? [["Excluded for chronology", count(artifact.embargoed_count)]] : []),
    [coach ? "Forward study cutoff" : native ? "Validation starts" : "Recorded cutoff", cutoff === null ? "Unavailable" : new Date(cutoff).toLocaleString()],
    [discovery ? "Usable evidence period" : coach ? "Forward study period" : "Recorded evidence period", period],
  ];
  return <section className="learning-fit-details" aria-label="Saved learning evidence">
    <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <p>{discovery
      ? "The Entry window counts resolved observations, including unavailable outcomes. These usable outcomes are split into training, validation and rows excluded to keep later outcomes out of training. The period describes usable evidence, not the full resolved window."
      : sizing
        ? "Policy observations include unavailable outcomes. Training needs usable size targets; validation includes its whole selected cohort. Rows without a usable target are separate from chronology exclusions."
        : contextual
          ? "Each horizon fits only its usable outcomes within this training cohort. Per-horizon fit counts were not saved. Validation retains unavailable outcomes in its coverage denominator."
          : exit
            ? "Timing is selected on the training cohort and checked on later Policy observations. Unavailable outcomes remain in the timing proof."
            : coach
              ? "Historical screening and the later forward study are separate evidence populations; these counts are not a regression training split."
              : "Saved counts belong to this generation. Detailed population definitions are unavailable for this historical format."}</p>
    <p>Saved evidence explains the candidate; qualification, Champion promotion and trading permission are checked separately.</p>
  </section>;
}

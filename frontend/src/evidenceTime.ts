export function savedTimestampMicros(value: string | null | undefined): bigint | null {
  if (typeof value !== "string") return null;
  // Python's saved clocks have at most six fractional digits. Date.parse alone
  // truncates those to milliseconds and normalizes invalid calendar dates.
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/i.exec(value);
  if (!match || value.startsWith("0000-")) return null;
  const base = `${match[1]}T${match[2]}`;
  const millis = Date.parse(`${base}Z`);
  if (!Number.isFinite(millis) || new Date(millis).toISOString().slice(0, 19) !== base) return null;
  const zone = match[4]!;
  let offsetMinutes = 0;
  if (zone.toUpperCase() !== "Z") {
    const hours = Number(zone.slice(1, 3));
    const minutes = Number(zone.slice(4, 6));
    if (hours >= 24 || minutes >= 60) return null;
    offsetMinutes = (hours * 60 + minutes) * (zone[0] === "-" ? -1 : 1);
  }
  return BigInt(millis) * 1000n - BigInt(offsetMinutes) * 60_000_000n
    + BigInt((match[3] ?? "").padEnd(6, "0"));
}

/** Use original aware clocks, never cached snapshot freshness or the viewer's clock. */
export function savedEvidenceAge(asOf: string, decisionAt: string | undefined): string {
  const observed = savedTimestampMicros(asOf);
  const decided = savedTimestampMicros(decisionAt);
  if (observed === null || decided === null) return "Age unavailable";
  const micros = decided - observed;
  if (micros < 0n) return "Measurement clock is after decision";
  return `${(Number(micros) / 1_000_000).toFixed(1)}s old at decision`;
}

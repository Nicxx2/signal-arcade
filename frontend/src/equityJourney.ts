import type { EquityPoint } from "./types";

export function buildEquityJourney(points: EquityPoint[], maxPoints = 240): EquityPoint[] {
  if (!points.length) return [];
  const changes = [points[0]!];
  for (const point of points.slice(1)) {
    if (point.equity_lamports !== changes.at(-1)!.equity_lamports) changes.push(point);
  }
  if (changes.length <= maxPoints || maxPoints < 4) return changes.slice(0, maxPoints);

  const first = changes[0]!;
  const last = changes.at(-1)!;
  const interior = changes.slice(1, -1);
  const bucketCount = Math.max(1, Math.floor((maxPoints - 2) / 2));
  const bucketSize = Math.ceil(interior.length / bucketCount);
  const sampled: EquityPoint[] = [first];
  for (let index = 0; index < interior.length; index += bucketSize) {
    const bucket = interior.slice(index, index + bucketSize);
    if (!bucket.length) continue;
    let minimum = bucket[0]!;
    let maximum = bucket[0]!;
    for (const point of bucket.slice(1)) {
      if (point.equity_lamports < minimum.equity_lamports) minimum = point;
      if (point.equity_lamports > maximum.equity_lamports) maximum = point;
    }
    if (minimum === maximum) sampled.push(minimum);
    else if (bucket.indexOf(minimum) < bucket.indexOf(maximum)) sampled.push(minimum, maximum);
    else sampled.push(maximum, minimum);
  }
  if (sampled.at(-1) !== last) sampled.push(last);
  return sampled.slice(0, maxPoints);
}

export function unchangedEquitySeconds(points: EquityPoint[]): number {
  if (points.length < 2) return 0;
  const latest = points.at(-1)!;
  let runStarted = latest;
  for (let index = points.length - 2; index >= 0; index -= 1) {
    const point = points[index]!;
    if (point.equity_lamports !== latest.equity_lamports) break;
    runStarted = point;
  }
  const latestAt = Date.parse(latest.recorded_at);
  const startedAt = Date.parse(runStarted.recorded_at);
  return Number.isFinite(latestAt) && Number.isFinite(startedAt)
    ? Math.max(0, (latestAt - startedAt) / 1_000)
    : 0;
}

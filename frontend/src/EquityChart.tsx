import { useId, useMemo, useState } from "react";
import { CircleHelp } from "lucide-react";
import { buildEquityJourney } from "./equityJourney";
import type { EquityPoint, QuoteCurrency } from "./types";

export function validEquityPoints(points: EquityPoint[]): EquityPoint[] {
  return points.filter((point) => Number.isFinite(Date.parse(point.recorded_at))
    && Number.isFinite(point.equity_lamports) && Number.isFinite(point.cash_lamports))
    .slice().sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at));
}

export function EquityChart({ points, currency, decimals, starting, peak, tall = false }: {
  points: EquityPoint[]; currency: QuoteCurrency; decimals: number;
  starting: number; peak?: number; tall?: boolean;
}) {
  const gradientId = useId();
  const helpId = useId();
  const [helpOpen, setHelpOpen] = useState(false);
  const [view, setView] = useState<"journey" | "time">("journey");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const clean = useMemo(() => validEquityPoints(points), [points]);
  const data = useMemo(() => view === "journey" ? buildEquityJourney(clean) : clean, [clean, view]);
  const pointKeys = useMemo(() => {
    // Several persisted observations may share a timestamp. Keep their values
    // distinct, and make identical repeats navigable in the Timeline view.
    const occurrences = new Map<string, number>();
    return data.map((point) => {
      const identity = JSON.stringify([point.kind ?? "checkpoint", point.recorded_at,
        point.equity_lamports, point.cash_lamports]);
      const occurrence = occurrences.get(identity) ?? 0;
      occurrences.set(identity, occurrence + 1);
      return `${identity}:${occurrence}`;
    });
  }, [data]);
  const selectedIndex = selectedKey === null ? -1 : pointKeys.indexOf(selectedKey);
  const selected = selectedIndex >= 0 ? data[selectedIndex] : undefined;
  const displayPoint = selected ?? data.at(-1);
  const amount = (value: number) => `${(value / 10 ** decimals).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: currency === "SOL" ? 5 : 2,
  })} ${currency}`;
  const values = data.map((point) => point.equity_lamports);
  const low = values.length ? Math.min(...values, starting) : starting;
  const high = values.length ? Math.max(...values, starting) : starting;
  const padding = Math.max((high - low) * 0.1, Math.abs(high) * 0.005, 1);
  const minimum = low - padding;
  const maximum = high + padding;
  const width = 640, height = tall ? 260 : 180, left = 8, right = width - 8, top = 12, bottom = height - 12;
  const firstTime = data.length ? Date.parse(data[0]!.recorded_at) : 0;
  const lastTime = data.length ? Date.parse(data.at(-1)!.recorded_at) : 0;
  const xAt = (index: number) => data.length === 1 ? width / 2 : left + (right - left) * (
    view === "time" && lastTime > firstTime
      ? (Date.parse(data[index]!.recorded_at) - firstTime) / (lastTime - firstTime)
      : index / Math.max(1, data.length - 1));
  const yAt = (value: number) => bottom - (value - minimum) / (maximum - minimum) * (bottom - top);
  const path = data.map((point, index) => `${index ? "L" : "M"}${xAt(index)},${yAt(point.equity_lamports)}`).join(" ");
  const timeLabel = (point: EquityPoint) => point.kind === "hourly_close"
    ? `Hourly close · ${new Date(point.recorded_at).toLocaleString()}–${point.period_end ? new Date(point.period_end).toLocaleTimeString() : "end of hour"}`
    : new Date(point.recorded_at).toLocaleString();
  const chooseNearest = (clientX: number, element: SVGSVGElement) => {
    if (!data.length) return;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0) return;
    const x = (clientX - rect.left) / rect.width * width;
    let nearest = 0;
    for (let index = 1; index < data.length; index++) {
      if (Math.abs(xAt(index) - x) < Math.abs(xAt(nearest) - x)) nearest = index;
    }
    setSelectedKey(pointKeys[nearest]!);
  };
  return <div className="equity-chart-shell">
    <div className="equity-chart-facts"><span>Started <strong>{amount(starting)}</strong></span>
      {peak !== undefined && Number.isFinite(peak) && <span>Season peak <strong>{amount(peak)}</strong></span>}
    </div>
    <div className="equity-chart-toolbar"><small>{view === "journey" ? "Equity changes · quiet periods collapsed" : "Time spacing · quiet periods preserved"}</small>
      <div className="equity-chart-controls">
        <div className="equity-chart-spacing" role="group" aria-label="Equity chart spacing">{(["journey", "time"] as const).map((mode) => <button type="button" key={mode} aria-pressed={view === mode} className={view === mode ? "active" : ""} onClick={() => { setView(mode); setSelectedKey(null); }}>{mode === "journey" ? "Journey" : "Timeline"}</button>)}</div>
        <button type="button" className="equity-chart-help-toggle" aria-label="Chart help" title="Chart help" aria-expanded={helpOpen} aria-controls={helpId} onClick={() => setHelpOpen((open) => !open)} onKeyDown={(event) => { if (event.key === "Escape") setHelpOpen(false); }}><CircleHelp size={16} aria-hidden="true" /></button>
      </div>
    </div>
    <div id={helpId} className="equity-chart-help" hidden={!helpOpen}>
      <p>Hover, tap or use arrow keys to inspect saved equity and cash values.</p>
      <p>Dashed line: starting bankroll. Lines connect saved observations. The scale covers displayed history and starting bankroll; the season peak covers the whole season.</p>
      {clean.some((point) => point.kind === "hourly_close") && <p>Older history uses hourly closing values; exact checkpoint times are unavailable within those hours. This view may cover only part of a long season.</p>}
    </div>
    {!data.length ? <p className="equity-chart-empty">Waiting for the first equity checkpoint.</p> : <>
      <div className="equity-chart-plot">
        <div className="equity-chart-axis" role="group" aria-label="Equity chart scale">
          {yAt(low) - yAt(high) < 52 ? <div className="equity-chart-axis-label compact" style={{ top: "50%" }}>
            {low === high ? <><span>Flat scale</span><strong>{amount(high)}</strong></>
              : <><span>Scale high</span><strong>{amount(high)}</strong><span>Scale low</span><strong>{amount(low)}</strong></>}
          </div> : <>
            <div className="equity-chart-axis-label" style={{ top: `${yAt(high) / height * 100}%` }}><span>Scale high</span><strong>{amount(high)}</strong></div>
            <div className="equity-chart-axis-label" style={{ top: `${yAt(low) / height * 100}%` }}><span>Scale low</span><strong>{amount(low)}</strong></div>
          </>}
        </div>
      <svg className={`equity-chart interactive ${tall ? "tall" : ""}`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
        role="slider" tabIndex={0} aria-label="Inspect paper equity checkpoints" aria-valuemin={1} aria-valuemax={data.length}
        aria-valuenow={selectedIndex >= 0 ? selectedIndex + 1 : data.length}
        aria-valuetext={`${timeLabel(selected ?? data.at(-1)!)} · Equity ${amount((selected ?? data.at(-1)!).equity_lamports)}`}
        onPointerMove={(event) => { if (event.pointerType === "mouse" || event.buttons) chooseNearest(event.clientX, event.currentTarget); }}
        onPointerDown={(event) => chooseNearest(event.clientX, event.currentTarget)}
        onPointerLeave={(event) => { if (event.pointerType === "mouse") setSelectedKey(null); }}
        onFocus={() => { if (selectedIndex < 0) setSelectedKey(pointKeys.at(-1)!); }}
        onKeyDown={(event) => {
          if (event.key === "Escape") { setSelectedKey(null); return; }
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const current = selectedIndex >= 0 ? selectedIndex : data.length - 1;
          const next = event.key === "Home" ? 0 : event.key === "End" ? data.length - 1 : Math.max(0, Math.min(data.length - 1, current + (event.key === "ArrowLeft" ? -1 : 1)));
          setSelectedKey(pointKeys[next]!);
        }}>
        <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7b74ff" stopOpacity=".26" /><stop offset="100%" stopColor="#7b74ff" stopOpacity="0" /></linearGradient></defs>
        {[low, high].map((value, index) => <line key={index} x1={left} x2={right} y1={yAt(value)} y2={yAt(value)} stroke="#29334b" vectorEffect="non-scaling-stroke" />)}
        <line x1={left} x2={right} y1={yAt(starting)} y2={yAt(starting)} stroke="#72839b" strokeDasharray="4 5" vectorEffect="non-scaling-stroke" />
        {data.length > 1 && <path d={`${path} L${xAt(data.length - 1)},${bottom} L${xAt(0)},${bottom} Z`} fill={`url(#${gradientId})`} />}
        <path d={path} fill="none" stroke="#968fff" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {data.length === 1 && <circle cx={xAt(0)} cy={yAt(data[0]!.equity_lamports)} r="3" fill="#b6fff0" />}
        {selected && <g><line x1={xAt(selectedIndex)} x2={xAt(selectedIndex)} y1={top} y2={bottom} stroke="#8dafba" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" /><circle cx={xAt(selectedIndex)} cy={yAt(selected.equity_lamports)} r="4" fill="#b6fff0" /></g>}
      </svg>
      </div>
      <div className="equity-chart-dates"><span>{new Date(data[0]!.recorded_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}</span><span>{new Date(clean.at(-1)!.recorded_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}</span></div>
      {displayPoint && <div className="equity-chart-inspection"><strong><span>{selected ? "Selected" : "Latest shown"} · </span>{amount(displayPoint.equity_lamports)} equity <span>· {amount(displayPoint.cash_lamports)} cash</span></strong><small>{timeLabel(displayPoint)}</small>{displayPoint.kind === "hourly_close" && displayPoint.high_equity_lamports !== undefined && displayPoint.low_equity_lamports !== undefined && <small>Hour range {amount(displayPoint.low_equity_lamports)}–{amount(displayPoint.high_equity_lamports)}</small>}</div>}
    </>}
  </div>;
}

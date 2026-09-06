import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw } from "lucide-react";
import { recordedDate } from "./model";
import type { ArenaView } from "./model";
import { replayTrail } from "./replay";
import { edgeText } from "./readout";
import type { useBattleReplay } from "./useBattleReplay";

export default function ArenaReplay({ replay, view, reduced, onMotion }: { replay: ReturnType<typeof useBattleReplay>; view: ArenaView; reduced: boolean; onMotion: (moving: boolean) => void }) {
  const { timeline, index, playing } = replay;
  if (!timeline) return replay.note ? <p className="ca-replay-note">{replay.note}</p> : null;
  const trail = replayTrail(timeline, index);
  const current = timeline.points[index]!;
  const seek = (value: number) => { replay.seek(value); onMotion(false); };
  return <section className="ca-replay" aria-label="Recorded battle playback">
    <div className="ca-replay-heading"><strong>Recorded comparison</strong><span>{index === timeline.points.length - 1 ? `Final result · ${view.outcome === "promoted" ? "New Champion" : view.outcome === "defended" ? "Champion retained" : "Inconclusive"}` : `Checkpoint ${index + 1} / ${timeline.points.length}`}</span></div>
    <div className="ca-replay-trail">
      <div><span>Recorded average difference</span><strong>{current.usable} usable · {edgeText(current.usable > 0 ? current.mean : null)}</strong></div>
      <svg viewBox="0 0 300 88" role="img" aria-label={`Recorded average difference, minus 5 to plus 5 percentage points. ${trail.summary} Dots are saved checkpoints in order; lines only connect adjacent known values. Values beyond the scale are clipped visually.`}>
        <line x1="10" y1="44" x2="290" y2="44" className="ca-trail-zero" />
        <text x="10" y="9">Contender +5 pp</text><text x="10" y="85">Champion −5 pp</text><text x="290" y="41" textAnchor="end">Level</text>
        {trail.dots.map((dot, i) => dot && <g key={i} style={{ color: dot.mean > 0 ? view.right?.color : dot.mean < 0 ? view.left?.color : "#b6ded8" }}>
          {trail.dots[i - 1] && <line x1={trail.dots[i - 1]!.x} y1={trail.dots[i - 1]!.y} x2={dot.x} y2={dot.y} />}
          <circle cx={dot.x} cy={dot.y} r={i === index ? 4 : 2.5}><title>{`Checkpoint ${i + 1}: ${edgeText(dot.mean)}`}</title></circle>
        </g>)}
      </svg>
      <p>{trail.summary}{trail.hasGap ? " Unavailable estimates leave gaps." : ""}</p>
    </div>
    <div className="ca-replay-controls">
      <button disabled={reduced} onClick={() => { if (playing) replay.pause(); else replay.play(); onMotion(!playing); }}>{playing ? <Pause size={14} /> : index === timeline.points.length - 1 ? <RotateCcw size={14} /> : <Play size={14} />}{playing ? "Pause replay" : index === timeline.points.length - 1 ? "Replay comparison" : "Play checkpoints"}</button>
      <button aria-label="Previous checkpoint" disabled={index === 0} onClick={() => seek(index - 1)}><ChevronLeft size={17} /></button>
      <input aria-label="Recorded checkpoint" type="range" min={0} max={timeline.points.length - 1} step={1} value={index} aria-valuetext={`Checkpoint ${index + 1} of ${timeline.points.length}, ${recordedDate(timeline.points[index]!.at)}${index === timeline.points.length - 1 ? ", final result" : ""}`} onChange={event => seek(Number(event.target.value))} />
      <button aria-label="Next checkpoint" disabled={index === timeline.points.length - 1} onClick={() => seek(index + 1)}><ChevronRight size={17} /></button>
      <button disabled={index === timeline.points.length - 1} onClick={() => seek(timeline.points.length - 1)}>Result</button>
    </div>
    <p>{recordedDate(timeline.points[index]!.at)} · {timeline.points.length} saved checkpoints · Time compressed.</p>
    <p>{timeline.partial ? "Partial recording: some earlier evidence or updates may be missing. The shown checkpoints are saved measurements. " : ""}{timeline.sampled ? "Selected checkpoints; values between them are not reconstructed. " : ""}Preliminary leads can reverse. Only the recorded result settles the battle. Fighter moves illustrate the evidence.{reduced ? " Reduced motion: use the arrows or slider." : ""}</p>
  </section>;
}

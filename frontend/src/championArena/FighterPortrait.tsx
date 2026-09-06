import type { CSSProperties } from "react";
import { Crown, ShieldCheck } from "lucide-react";
import type { ChallengerChampionRecord } from "../types";
import type { Fighter } from "./model";
import { makeFighter } from "./model";
import { EMBLEMS, VISORS, familyMark } from "./design";
import type { Segment } from "./design";

function Glyph({ segments, x, y, sx, sy, color, width = 2 }: { segments: readonly Segment[]; x: number; y: number; sx: number; sy: number; color: string; width?: number }) {
  return <g stroke={color} strokeWidth={width} strokeLinecap="round">{segments.map(([x1, y1, x2, y2], i) => <line key={i} x1={x + x1 * sx} y1={y - y1 * sy} x2={x + x2 * sx} y2={y - y2 * sy} />)}</g>;
}

/** Reuse the saved artifact's identity, including while its influence is suspended. */
export function ChampionRecordPortrait({ record }: { record: Pick<ChallengerChampionRecord, "skill" | "champion_version" | "champion_codename" | "model_family"> }) {
  if (!record.champion_version?.trim()) return <span className="ca-reign-portrait ca-reign-unknown" aria-hidden="true" title="Fighter identity unavailable"><ShieldCheck size={27} /></span>;
  const fighter = makeFighter(record.champion_version, record.champion_codename, record.model_family, record.skill);
  return <span className="ca-reign-portrait" aria-hidden="true" title={`${fighter.name} · ${fighter.signature}`} style={{ "--fighter-accent": fighter.color } as CSSProperties}>
    <FighterPortrait fighter={fighter} /><Crown className="ca-reign-crown" size={13} />
  </span>;
}

/** Original vector counterpart of the articulated 3D rig. No renderer or image fetch. */
export default function FighterPortrait({ fighter, full = false }: { fighter: Fighter; full?: boolean }) {
  return <svg className={`fighter-portrait ${full ? "full" : ""}`} viewBox={full ? "0 0 200 350" : "28 0 144 145"} aria-hidden="true" style={{ "--fighter-color": fighter.color, "--fighter-trim": fighter.trim } as CSSProperties}>
    <ellipse cx="100" cy="331" rx="62" ry="9" fill={fighter.color} opacity=".12" />
    <g stroke="#425064" strokeWidth="2" strokeLinejoin="round">
      {fighter.crest === 1 && <path d="M72 59 46 24 54 94 72 112 M128 59 154 24 146 94 128 112" fill="#202d40" />}
      {fighter.crest === 2 && <path d="M85 25 88 3 100 17 112 3 115 25" fill={fighter.color} stroke="none" />}
      {fighter.family === "XGBoost" && <path d="M58 48V30L50 22 M58 30 66 22 M142 48V30L150 22 M142 30 134 22" stroke={fighter.color} fill="none" strokeWidth="3" />}
      <path d="M65 142 73 205 127 205 135 142" fill="#142032" />
      <path d="M72 207 72 259 87 267 98 218 M102 218 113 267 128 259 128 207" fill="#304057" />
      <path d="M74 267 70 312 90 314 93 273 M107 273 110 314 130 312 126 267" fill="#1d2b40" />
      <path d="M69 307 59 325 91 325 92 307 M108 307 109 325 141 325 131 307" fill="#34455e" />
      <path d="M45 128 34 171 46 179 62 147 M155 128 166 171 154 179 138 147" fill="#2a394e" />
      <path d="M34 180 31 222 47 228 51 185 M149 185 153 228 169 222 166 180" fill="#384b65" />
      <path d="M30 222 29 237 46 241 49 226 M151 226 154 241 171 237 170 222" fill="#101a2b" />
      <path d={fighter.build === 2 ? "M70 104 47 93 26 109 32 143 60 144 M130 104 153 93 174 109 168 143 140 144" : "M70 108 47 99 32 114 38 138 62 139 M130 108 153 99 168 114 162 138 138 139"} fill="#41536a" />
      {fighter.details.shoulders === 1 && <path d="M34 113 47 106 60 114 59 122 46 115 36 122 M166 113 153 106 140 114 141 122 154 115 164 122" fill={fighter.color} />}
      {fighter.details.shoulders === 2 && <path d="M35 111 33 93 51 100 59 110 M165 111 167 93 149 100 141 110" fill="#60758b" />}
      {fighter.details.shoulders === 3 && <path d="M36 115 43 108 54 112 54 129 43 133 36 126Z M164 115 157 108 146 112 146 129 157 133 164 126Z" fill="#18263a" stroke={fighter.color} />}
      <path d="M66 99 84 88 116 88 134 99 130 149 100 166 70 149Z" fill="#304259" />
      <path d="M73 108 100 118 127 108 123 138 100 151 77 138Z" fill="#152135" />
      <Glyph segments={EMBLEMS[fighter.details.emblem]!} x={100} y={129} sx={18} sy={13} color={fighter.color} />
      <Glyph segments={familyMark(fighter.family)} x={100} y={129} sx={17} sy={16} color={fighter.trim} width={2.6} />
      {fighter.details.trim === 1 && <path d="M75 106 83 110 M117 110 125 106 M80 149 88 153 M112 153 120 149" stroke={fighter.color} fill="none" />}
      {fighter.details.trim === 2 && <path d="M73 108 76 124 M127 108 124 124 M92 157H108" stroke={fighter.color} fill="none" />}
      <path d="M78 176 100 187 122 176 120 194 100 202 80 194Z" fill="#35485f" />
      <path d="M94 83H106V99H94Z" fill="#111b2a" />
      <path d="M78 23 100 15 122 23 128 53 119 79 100 88 81 79 72 53Z" fill="#394e66" />
      {fighter.details.helmet === 1 && <path d="M77 37 80 22 100 18 120 22 123 37 100 30Z" fill="#60758b" />}
      {fighter.details.helmet === 2 && <path d="M73 42 81 52 84 74 77 68 M127 42 119 52 116 74 123 68" fill={fighter.color} />}
      {fighter.details.helmet === 3 && <path d="M94 19 100 13 106 19 106 38 100 43 94 38Z" fill={fighter.color} />}
      <path d="M78 42 100 47 122 42 118 61 100 71 82 61Z" fill="#101a2a" />
      <Glyph segments={VISORS[fighter.details.visor]!} x={100} y={52} sx={21} sy={16} color={fighter.color} width={3.5} />
      <path d="M87 27 100 23 113 27 M77 274 77 297 M123 274 123 297 M39 193 38 212 M161 193 162 212" stroke={fighter.color} strokeWidth="3" fill="none" />
      {fighter.build === 0 && <path d="M44 173 21 153 17 204 39 227Z" fill={fighter.color} fillOpacity=".23" stroke={fighter.color} />}
    </g>
  </svg>;
}

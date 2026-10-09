import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { areaPath, scale, shortDate, smoothPath } from "./chartUtils";
import type { Point } from "./chartUtils";

export interface TrendDatum {
  label: string;
  /** ISO date for the axis tick. */
  date: string | null;
  /** null = this session has no generated report. Rendered as a gap, not a zero. */
  value: number | null;
  href?: string;
}

const W = 560;
const H = 190;
const PAD = { top: 16, right: 12, bottom: 26, left: 30 };

/**
 * Score across recent interviews.
 *
 * Built on real per-session report scores — one point per completed session that
 * has a generated report. Sessions without one are **gaps in the line**, not
 * zeros: the line breaks and the point is hollow, because "no report was
 * generated" and "you scored nothing" are different facts and a chart that
 * conflates them is lying.
 *
 * Interaction is a hover band over the whole plot rather than tiny hit targets on
 * each point — at 4-6 points the nearest-x approach is both easier to hit and
 * what every serious charting UI does.
 */
export function TrendChart({ data }: { data: TrendDatum[] }) {
  const prefersReducedMotion = useReducedMotion();
  const [hover, setHover] = useState<number | null>(null);

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const baselineY = PAD.top + plotH;

  // Y always spans the full 0-100 scale. Auto-scaling to the data's own range
  // is the classic way to make a 3-point difference look like a cliff.
  const yFor = (value: number) => scale(value, 0, 100, baselineY, PAD.top);
  const xFor = (index: number) =>
    data.length === 1 ? PAD.left + plotW / 2 : PAD.left + (index / (data.length - 1)) * plotW;

  // Contiguous runs of real values. Each run is drawn as its own path so a gap
  // genuinely interrupts the line.
  const runs: { points: Point[]; startIndex: number }[] = [];
  let current: { points: Point[]; startIndex: number } | null = null;
  data.forEach((datum, index) => {
    if (datum.value === null) {
      current = null;
      return;
    }
    const point = { x: xFor(index), y: yFor(datum.value) };
    if (!current) {
      current = { points: [point], startIndex: index };
      runs.push(current);
    } else {
      current.points.push(point);
    }
  });

  const active = hover !== null ? data[hover] : null;
  const measured = data.filter((d) => d.value !== null);

  if (measured.length === 0) {
    return (
      <div className="flex h-[190px] flex-col items-center justify-center gap-1 text-center">
        <p className="text-text-muted">No scored interviews yet</p>
        <p className="text-[0.6875rem] text-text-subtle">
          Your score across sessions appears here once a report exists.
        </p>
      </div>
    );
  }

  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Interview score across recent sessions">
        <defs>
          <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--grad-a)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--grad-a)" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="trend-stroke" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--grad-a)" />
            <stop offset="100%" stopColor="var(--grad-b)" />
          </linearGradient>
        </defs>

        {/* Gridlines at 0/25/50/75/100, labelled so the scale is explicit. */}
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              y1={yFor(tick)}
              x2={W - PAD.right}
              y2={yFor(tick)}
              stroke="var(--color-border)"
              strokeWidth="1"
              strokeDasharray={tick === 0 ? undefined : "3 4"}
              opacity={tick === 0 ? 1 : 0.55}
            />
            <text
              x={PAD.left - 8}
              y={yFor(tick) + 3}
              textAnchor="end"
              className="fill-[var(--color-text-subtle)] text-[9px]"
            >
              {tick}
            </text>
          </g>
        ))}

        {runs.map((run, runIndex) => (
          <g key={runIndex}>
            {run.points.length > 1 && (
              <path d={areaPath(run.points, baselineY)} fill="url(#trend-fill)" />
            )}
            <motion.path
              d={smoothPath(run.points)}
              fill="none"
              stroke="url(#trend-stroke)"
              strokeWidth="2"
              strokeLinecap="round"
              initial={prefersReducedMotion ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
            />
          </g>
        ))}

        {/* Points. Hollow where no report exists. */}
        {data.map((datum, index) => {
          const isActive = hover === index;
          const y = datum.value === null ? baselineY : yFor(datum.value);
          return (
            <g key={index}>
              {isActive && datum.value !== null && (
                <line
                  x1={xFor(index)}
                  y1={PAD.top}
                  x2={xFor(index)}
                  y2={baselineY}
                  stroke="var(--color-accent)"
                  strokeWidth="1"
                  opacity="0.35"
                />
              )}
              <circle
                cx={xFor(index)}
                cy={y}
                r={isActive ? 5 : 3.5}
                fill={datum.value === null ? "var(--color-bg)" : "var(--color-accent)"}
                stroke={datum.value === null ? "var(--color-border-strong)" : "var(--color-bg)"}
                strokeWidth={datum.value === null ? 1.5 : 2}
                strokeDasharray={datum.value === null ? "2 2" : undefined}
                className="transition-[r] duration-150"
              />
              <text
                x={xFor(index)}
                y={H - 8}
                textAnchor="middle"
                className="fill-[var(--color-text-subtle)] text-[9px]"
              >
                {shortDate(datum.date)}
              </text>
            </g>
          );
        })}

        {/* Hover bands — one invisible column per point, full plot height. */}
        {data.map((_, index) => {
          const bandW = plotW / Math.max(1, data.length);
          return (
            <rect
              key={`band-${index}`}
              x={xFor(index) - bandW / 2}
              y={PAD.top}
              width={bandW}
              height={plotH}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}
      </svg>

      {/* Tooltip. Positioned in DOM rather than SVG so it can use real type. */}
      {active && (
        <div
          className="pointer-events-none absolute -top-1 rounded-control border border-border bg-bg-elevated px-2.5 py-1.5 shadow-[var(--shadow-md)]"
          style={{
            left: `${(xFor(hover!) / W) * 100}%`,
            transform: "translateX(-50%)",
          }}
        >
          <p className="max-w-[12rem] truncate text-[0.75rem] font-medium text-text">{active.label}</p>
          <p className="text-[0.6875rem] text-text-subtle">
            {active.value === null ? "No report generated" : `Score ${Math.round(active.value)} · ${shortDate(active.date)}`}
          </p>
        </div>
      )}
    </div>
  );
}

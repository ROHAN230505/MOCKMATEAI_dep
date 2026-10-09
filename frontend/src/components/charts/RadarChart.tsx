import { motion, useReducedMotion } from "framer-motion";
import { radarAxis, radarPoints, toPolygon } from "./chartUtils";

export interface RadarAxisDatum {
  label: string;
  /** null = not measured. Plotted at the centre and marked, never as a score. */
  value: number | null;
}

const SIZE = 240;
const CENTER = SIZE / 2;
const RADIUS = 78;
const RINGS = [0.25, 0.5, 0.75, 1];

/**
 * Skill radar across the report's scored categories.
 *
 * ## The unmeasured problem
 *
 * A radar chart has no way to express "no data" — a missing axis collapses to the
 * centre, which is visually identical to scoring zero. That's unacceptable here,
 * so unmeasured axes are handled explicitly: the polygon is drawn only through
 * the measured axes, and each unmeasured axis gets a dashed spoke and a hollow
 * marker with its label greyed. The shape therefore describes only what was
 * actually measured, and the gaps are legible as gaps.
 */
export function RadarChart({ data }: { data: RadarAxisDatum[] }) {
  const prefersReducedMotion = useReducedMotion();
  const axes = radarAxis(data.length, RADIUS, CENTER, CENTER);
  const measuredIndices = data.map((d, i) => (d.value !== null ? i : -1)).filter((i) => i >= 0);

  // The polygon spans only measured axes. With fewer than three it isn't a
  // shape, so those render as points on their spokes instead.
  const polygon =
    measuredIndices.length >= 3
      ? toPolygon(
          radarPoints(
            data.map((d) => d.value ?? 0),
            RADIUS,
            CENTER,
            CENTER,
          ).filter((_, i) => measuredIndices.includes(i)),
        )
      : null;

  const valuePoints = radarPoints(
    data.map((d) => d.value ?? 0),
    RADIUS,
    CENTER,
    CENTER,
  );

  return (
    <div className="flex flex-col items-center">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-[240px]" role="img" aria-label="Skill breakdown">
        <defs>
          <linearGradient id="radar-fill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--grad-a)" stopOpacity="0.42" />
            <stop offset="100%" stopColor="var(--grad-b)" stopOpacity="0.18" />
          </linearGradient>
        </defs>

        {/* Web */}
        {RINGS.map((ring) => (
          <polygon
            key={ring}
            points={toPolygon(radarAxis(data.length, RADIUS * ring, CENTER, CENTER))}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth="1"
            opacity={ring === 1 ? 1 : 0.5}
          />
        ))}

        {/* Spokes — dashed where the axis has no data. */}
        {axes.map((axis, index) => (
          <line
            key={index}
            x1={CENTER}
            y1={CENTER}
            x2={axis.x}
            y2={axis.y}
            stroke="var(--color-border)"
            strokeWidth="1"
            strokeDasharray={data[index].value === null ? "3 3" : undefined}
            opacity={data[index].value === null ? 0.8 : 0.5}
          />
        ))}

        {polygon && (
          <motion.polygon
            points={polygon}
            fill="url(#radar-fill)"
            stroke="var(--color-accent)"
            strokeWidth="1.75"
            strokeLinejoin="round"
            initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            style={{ transformOrigin: `${CENTER}px ${CENTER}px` }}
          />
        )}

        {/* Vertex markers */}
        {data.map((datum, index) =>
          datum.value === null ? (
            <circle
              key={index}
              cx={axes[index].x}
              cy={axes[index].y}
              r={3}
              fill="var(--color-bg)"
              stroke="var(--color-border-strong)"
              strokeWidth="1.5"
              strokeDasharray="2 2"
            />
          ) : (
            <circle
              key={index}
              cx={valuePoints[index].x}
              cy={valuePoints[index].y}
              r={3.5}
              fill="var(--color-accent)"
              stroke="var(--color-bg)"
              strokeWidth="1.5"
            />
          ),
        )}
      </svg>

      {/* Legend. Carries the numbers — reading a value off a radar's geometry is
          guesswork, so the shape shows the balance and the list shows the data. */}
      <ul className="mt-3 grid w-full grid-cols-2 gap-x-4 gap-y-1.5">
        {data.map((datum) => (
          <li key={datum.label} className="flex items-center justify-between gap-2">
            <span
              className={`truncate text-[0.75rem] ${datum.value === null ? "text-text-subtle" : "text-text-muted"}`}
            >
              {datum.label}
            </span>
            <span
              className={`stat shrink-0 text-[0.75rem] ${datum.value === null ? "text-text-subtle" : "text-text"}`}
            >
              {datum.value === null ? "—" : Math.round(datum.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

import { useCountUp } from "../hooks/useCountUp";

const SIZE = 168;
const STROKE = 10;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * The circular Readiness Index indicator (Section 4.5) — counts up from 0 on
 * load.
 *
 * Built as a single SVG with a gradient-stroked arc over a full track, and the
 * number stacked in the middle via absolute positioning rather than the old
 * negative-margin trick — so the ring stays centred at any size and the label
 * can't collide with the digits.
 *
 * The gradient id is suffixed per-instance because two rings on one page
 * (report + dashboard) would otherwise share one def and the second would
 * silently inherit the first's stops.
 */
export function ReadinessRing({
  score,
  label,
  size = SIZE,
  caption,
}: {
  score: number;
  label: string;
  size?: number;
  /** Replaces the "/ 100" line when the context needs something else. */
  caption?: string;
}) {
  const animated = useCountUp(score);
  const offset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(100, animated)) / 100);
  const gradientId = `readiness-gradient-${Math.round(size)}`;

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`} className="-rotate-90" aria-hidden="true">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--grad-a)" />
              <stop offset="100%" stopColor="var(--grad-b)" />
            </linearGradient>
          </defs>
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke="var(--color-surface-raised)"
            strokeWidth={STROKE}
            fill="none"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke={`url(#${gradientId})`}
            strokeWidth={STROKE}
            strokeLinecap="round"
            fill="none"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
          />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="tnum text-[2.5rem] leading-none font-semibold text-text">{Math.round(animated)}</span>
          <span className="mt-1 text-xs text-text-subtle">{caption ?? "/ 100"}</span>
        </div>
      </div>

      <p className="text-sm font-medium text-text-muted">{label}</p>
    </div>
  );
}

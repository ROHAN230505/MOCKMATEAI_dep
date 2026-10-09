import { motion, useReducedMotion } from "framer-motion";
import { useCountUp } from "../../hooks/useCountUp";

export interface SkillNode {
  id: string;
  label: string;
  /** 0-100, or null when nothing measured it. Never substitute a number here. */
  score: number | null;
  /** Why it's unmeasured, shown when the node is selected. */
  note?: string;
}

const SIZE = 200;
const CENTER = SIZE / 2;
const RING_RADIUS = 78;
const RING_STROKE = 7;
const CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

/**
 * The readiness centrepiece: an animated ring with the skill nodes that feed it
 * orbiting around the outside.
 *
 * ## The rule this component exists to enforce
 *
 * A node with `score: null` was **not measured** — it is not a zero. It renders
 * as a hollow, dashed node with an em dash, sits at a fixed neutral position on
 * the ring, and states why when selected. Plotting it at 0 would read as "you
 * scored nothing at communication" when the truth is "this session captured no
 * audio prosody". That distinction is the whole point of the visualisation.
 *
 * Nodes are laid out on a circle by index rather than by value, so position
 * carries no meaning that could be misread — only the fill arc and the number do.
 */
export function ReadinessVisualization({
  score,
  label,
  skills,
  selected,
  onSelect,
}: {
  score: number;
  label: string;
  skills: SkillNode[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const prefersReducedMotion = useReducedMotion();
  const animated = useCountUp(score);
  const offset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(100, animated)) / 100);
  const active = skills.find((s) => s.id === selected) ?? null;

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="overflow-visible">
          <defs>
            <linearGradient id="readiness-arc" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--grad-a)" />
              <stop offset="60%" stopColor="var(--grad-b)" />
              <stop offset="100%" stopColor="var(--grad-c)" />
            </linearGradient>
            <filter id="readiness-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Track */}
          <circle
            cx={CENTER}
            cy={CENTER}
            r={RING_RADIUS}
            fill="none"
            stroke="var(--color-surface-raised)"
            strokeWidth={RING_STROKE}
          />

          {/* Value arc */}
          <motion.circle
            cx={CENTER}
            cy={CENTER}
            r={RING_RADIUS}
            fill="none"
            stroke="url(#readiness-arc)"
            strokeWidth={RING_STROKE}
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            filter="url(#readiness-glow)"
            transform={`rotate(-90 ${CENTER} ${CENTER})`}
          />

          {/* Skill nodes, evenly spaced. Position is index-based and carries no
              meaning — only the fill and the number do. */}
          {skills.map((skill, index) => {
            const angle = (index / skills.length) * Math.PI * 2 - Math.PI / 2;
            const r = RING_RADIUS + 20;
            const x = CENTER + Math.cos(angle) * r;
            const y = CENTER + Math.sin(angle) * r;
            const measured = skill.score !== null;
            const isActive = skill.id === selected;

            return (
              <g
                key={skill.id}
                transform={`translate(${x} ${y})`}
                className="cursor-pointer"
                onClick={() => onSelect(isActive ? null : skill.id)}
                role="button"
                tabIndex={0}
                aria-label={`${skill.label}: ${measured ? Math.round(skill.score!) : "not measured"}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(isActive ? null : skill.id);
                  }
                }}
              >
                {/* Spoke back to the ring */}
                <line
                  x1={-Math.cos(angle) * 15}
                  y1={-Math.sin(angle) * 15}
                  x2={0}
                  y2={0}
                  stroke={isActive ? "var(--color-accent)" : "var(--color-border)"}
                  strokeWidth={1}
                />
                <motion.circle
                  r={isActive ? 7 : 5}
                  fill={measured ? "var(--color-accent)" : "transparent"}
                  stroke={measured ? "var(--color-accent)" : "var(--color-border-strong)"}
                  strokeWidth={1.5}
                  strokeDasharray={measured ? undefined : "2 2"}
                  animate={
                    prefersReducedMotion || !measured ? undefined : { opacity: [0.75, 1, 0.75] }
                  }
                  transition={{ duration: 2.6, repeat: Infinity, delay: index * 0.25 }}
                />
              </g>
            );
          })}
        </svg>

        {/* Centre readout */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="stat text-[2.75rem] leading-none text-text">{Math.round(animated)}</span>
          <span className="mt-1 text-[0.625rem] text-text-subtle">out of 100</span>
        </div>
      </div>

      <span className="mt-1 rounded-pill border border-accent/30 bg-accent-soft px-2.5 py-0.5 text-[0.6875rem] font-medium text-accent">
        {label}
      </span>

      {/* Selected-node detail. Reserves its own height so selecting a node never
          shifts the layout around it. */}
      <div className="mt-3 flex min-h-[2.5rem] w-full max-w-[15rem] flex-col items-center justify-center text-center">
        {active ? (
          <>
            <p className="text-[0.8125rem] font-medium text-text">
              {active.label}
              {active.score !== null && (
                <span className="stat ml-2 text-accent">{Math.round(active.score)}</span>
              )}
            </p>
            <p className="mt-0.5 text-[0.6875rem] leading-relaxed text-text-muted">
              {active.score !== null
                ? "From your most recent scored interview."
                : (active.note ?? "Not measured yet.")}
            </p>
          </>
        ) : (
          <p className="text-[0.6875rem] text-text-subtle">Select a node for detail</p>
        )}
      </div>
    </div>
  );
}

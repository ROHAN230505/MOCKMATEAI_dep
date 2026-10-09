import { Link } from "react-router-dom";
import type { CategoryDelta, FeedbackComparison } from "../../types/feedback";

const CATEGORY_LABELS: Record<string, string> = {
  overall: "Overall readiness",
  content: "Content",
  communication: "Communication",
  confidence: "Confidence",
  body_language: "Body language",
};

const DIRECTION_STYLES: Record<CategoryDelta["direction"], string> = {
  improved: "text-success",
  declined: "text-danger",
  unchanged: "text-text-muted",
  not_comparable: "text-text-subtle",
};

function formatDelta(delta: CategoryDelta): string {
  if (delta.direction === "not_comparable" || delta.delta === null) return "—";
  if (delta.direction === "unchanged") return "no real change";
  const sign = delta.delta > 0 ? "+" : "";
  return `${sign}${Math.round(delta.delta)}`;
}

function DirectionGlyph({ direction }: { direction: CategoryDelta["direction"] }) {
  if (direction === "not_comparable") return null;
  const path =
    direction === "improved" ? "M12 19V5m0 0-6 6m6-6 6 6" : direction === "declined" ? "M12 5v14m0 0 6-6m-6 6-6-6" : "M5 12h14";
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

/**
 * Section 4.11A's Before & After block.
 *
 * Rows the backend marked `not_comparable` show an em dash with an explanation
 * rather than a delta — a category that wasn't measured in one of the two
 * sessions has no meaningful difference, and "0" would read as "you stayed the
 * same" at something never observed.
 */
export function BeforeAfter({ comparison }: { comparison: FeedbackComparison }) {
  const comparable = comparison.deltas.filter((delta) => delta.direction !== "not_comparable");
  const incomparable = comparison.deltas.filter((delta) => delta.direction === "not_comparable");

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm leading-relaxed text-text">{comparison.headline}</p>

      <ul className="flex flex-col divide-y divide-border">
        {comparable.map((delta) => (
          <li key={delta.category} className="flex items-center justify-between gap-4 py-3 text-sm">
            <span className="text-text-muted">{CATEGORY_LABELS[delta.category] ?? delta.category}</span>
            <span className="flex items-center gap-3">
              <span className="tnum text-text-subtle">
                {delta.previous === null ? "—" : Math.round(delta.previous)}
                <span className="mx-1.5">→</span>
                <span className="font-medium text-text">
                  {delta.current === null ? "—" : Math.round(delta.current)}
                </span>
              </span>
              <span
                className={`inline-flex min-w-[6.5rem] items-center justify-end gap-1 font-medium ${DIRECTION_STYLES[delta.direction]}`}
              >
                <DirectionGlyph direction={delta.direction} />
                {formatDelta(delta)}
              </span>
            </span>
          </li>
        ))}
      </ul>

      {incomparable.length > 0 && (
        <p className="text-xs leading-relaxed text-text-subtle">
          No comparison for{" "}
          {incomparable.map((d) => (CATEGORY_LABELS[d.category] ?? d.category).toLowerCase()).join(" or ")} —
          neither session measured them.
        </p>
      )}

      <p className="text-xs leading-relaxed text-text-subtle">
        Compared against your{" "}
        <Link
          to={`/interview/feedback/${comparison.previousSessionId}`}
          className="font-medium text-accent hover:underline"
        >
          {comparison.previousRoleTarget} interview
        </Link>
        {comparison.previousCompletedAt
          ? ` from ${new Date(comparison.previousCompletedAt).toLocaleDateString()}`
          : ""}
        .
      </p>
    </div>
  );
}

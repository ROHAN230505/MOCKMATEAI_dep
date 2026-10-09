import { motion, useReducedMotion } from "framer-motion";
import { Badge } from "../ui/Badge";
import type { FeedbackItem } from "../../types/feedback";

const CATEGORY_LABELS: Record<FeedbackItem["category"], string> = {
  content: "Content",
  communication: "Communication",
  confidence: "Confidence",
  body_language: "Body language",
};

/**
 * Strengths or improvements, each with the evidence behind it (Section 4.11).
 *
 * The evidence line is not decoration: it's the quote from the candidate's own
 * answer that the claim rests on. Rendering it under every item is what lets
 * someone check the feedback instead of just believing it — and it's why the
 * backend refuses to persist an item that cites nothing. It's set as a real
 * blockquote so the distinction between our words and theirs is structural, not
 * just a lighter grey.
 */
export function FeedbackItemList({
  items,
  emptyMessage,
  tone = "accent",
}: {
  items: FeedbackItem[];
  emptyMessage: string;
  tone?: "accent" | "success";
}) {
  const prefersReducedMotion = useReducedMotion();

  if (items.length === 0) {
    return <p className="text-sm text-text-muted italic">{emptyMessage}</p>;
  }

  return (
    <ul className="flex flex-col gap-6">
      {items.map((item, index) => (
        <motion.li
          key={`${item.category}-${index}`}
          initial={prefersReducedMotion ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: prefersReducedMotion ? 0 : index * 0.05, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col gap-2.5"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={tone === "success" ? "success" : "accent"}>{CATEGORY_LABELS[item.category]}</Badge>
          </div>
          <p className="text-sm leading-relaxed text-text">{item.text}</p>
          {item.evidenceReference && (
            <blockquote className="border-l-2 border-border pl-4 text-xs leading-relaxed text-text-muted italic">
              {item.evidenceReference}
            </blockquote>
          )}
        </motion.li>
      ))}
    </ul>
  );
}

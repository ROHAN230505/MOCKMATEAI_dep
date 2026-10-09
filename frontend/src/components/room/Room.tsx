/**
 * The page's environment.
 *
 * This is what replaced the WebGL particle field, and the replacement is
 * deliberately not a smaller version of the same idea. A moving background
 * competes with the content for the one thing an interface cannot spare — the
 * reader's attention — and a network-of-nodes motif announces "this product
 * involves AI" to a user who already knows.
 *
 * What is here instead is closer to how a photographed interior reads: one
 * light source, a surface with tooth, and nothing else. Both layers are pure
 * CSS, static, and `pointer-events: none`, so the whole environment costs one
 * composited paint and zero frames thereafter. Removing the field also took
 * 866 KB of three.js off the first-paint path, which the landing page was
 * loading before it could show a single word.
 *
 * `aria-hidden` throughout: there is nothing here to describe.
 */
export function Room({
  className = "",
  /** `absolute` when the caller places this inside a panel rather than behind the page. */
  anchor = "fixed",
}: {
  className?: string;
  anchor?: "fixed" | "absolute";
}) {
  return (
    <div aria-hidden="true" className={`pointer-events-none ${anchor} inset-0 -z-10 overflow-hidden ${className}`}>
      <div className="ambient absolute inset-0" />
      <div className="grain absolute inset-0" />
    </div>
  );
}

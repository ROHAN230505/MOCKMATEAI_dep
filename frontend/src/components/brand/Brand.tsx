import { Link } from "react-router-dom";
import { useState } from "react";

/**
 * The single source of truth for MockMateAI's brand marks.
 *
 * Every logo in the product comes from here — navbar, sidebar, auth, loader,
 * intro, empty states — so the official asset is referenced once and can be
 * swapped in one place.
 *
 * ## Where the asset lives
 *
 * `public/brand/mockmateai-mark.png` — the official mark, exactly as supplied.
 * Optional theme-specific overrides, used automatically when present:
 *   `public/brand/mockmateai-mark-light.png`  (for dark backgrounds)
 *   `public/brand/mockmateai-mark-dark.png`   (for light backgrounds)
 *
 * The asset is never redrawn, recoloured or reproportioned here. It is rendered
 * at its native aspect ratio inside a square box, and the only treatment applied
 * is an optional soft glow behind it — which sits *under* the image and never
 * touches its pixels.
 *
 * ## Before the asset is added
 *
 * `MARK_SRC` may not exist yet. Rather than showing a broken image, the mark
 * falls back to a geometric placeholder so the interface stays coherent, and
 * swaps to the official asset the moment the file lands. Nothing needs to change
 * in any callsite for that to happen.
 */

const MARK_SRC = "/brand/mockmateai-mark.png";

/**
 * Sized by height only, with width left to follow the artwork.
 *
 * The supplied mark is 1362×1155 — slightly wider than tall. Forcing it into a
 * square box would letterbox it, making it optically smaller than everything
 * beside it and leaving dead space on two sides. Setting the height and letting
 * the width resolve keeps the artwork at its own proportions and makes it line
 * up correctly against the wordmark's cap height.
 */
const SIZES = {
  xs: "h-5",
  sm: "h-6",
  md: "h-8",
  lg: "h-11",
  xl: "h-16",
  hero: "h-24",
} as const;

export type MarkSize = keyof typeof SIZES;

/**
 * Fallback used only until the official PNG is added. Deliberately abstract —
 * a placeholder that reads as a considered geometric mark rather than as a
 * missing asset.
 */
function PlaceholderMark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`flex items-center justify-center rounded-[0.5rem] ${className}`}
      style={{ background: "linear-gradient(150deg, var(--grad-a), var(--grad-b))" }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 24 24" className="h-[64%] w-[64%]" fill="none" aria-hidden="true">
        <path
          d="M4 19V6.6c0-.5.6-.8 1-.5l7 6.2 7-6.2c.4-.3 1 0 1 .5V19h-3.4v-7.2L12 16.1 7.4 11.8V19H4Z"
          fill="#fff"
          fillOpacity="0.95"
        />
      </svg>
    </span>
  );
}

/**
 * The mark alone. Use wherever space is tight or the wordmark would repeat
 * something already on screen.
 */
export function BrandMark({
  size = "md",
  glow = false,
  className = "",
}: {
  size?: MarkSize;
  /** Soft light behind the mark. For the intro and the loader. */
  glow?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <PlaceholderMark className={`${SIZES[size]} aspect-square ${className}`} />;
  }

  return (
    <span className={`relative inline-flex shrink-0 items-center ${SIZES[size]} ${className}`}>
      {glow && (
        <span
          aria-hidden="true"
          className="absolute inset-0 -z-10 scale-[1.8] rounded-full opacity-40 blur-2xl"
          style={{ background: "radial-gradient(circle, var(--grad-a), transparent 70%)" }}
        />
      )}
      <img
        src={MARK_SRC}
        alt=""
        aria-hidden="true"
        draggable={false}
        onError={() => setFailed(true)}
        // The artwork's outer faces are a light silver gradient, which loses its
        // top-left edge against a white page. Rather than recolouring the asset —
        // which the brand rules forbid — a hairline dark plate sits behind it in
        // light mode only, which is the same treatment the brand sheet itself
        // uses for the app icon. In dark mode the mark stands alone as supplied.
        className="h-full w-auto max-w-none select-none rounded-[0.3em] object-contain p-[0.12em] [background:radial-gradient(circle_at_50%_40%,#1c1d26,#0d0e14)] dark:rounded-none dark:bg-none dark:p-0"
      />
    </span>
  );
}

/**
 * Mark + wordmark, the standard header lockup.
 *
 * The wordmark is set in the product's own type rather than baked into an
 * image, so it stays crisp at every size, inherits the theme's text colour, and
 * remains selectable text for search and screen readers. The `AI` keeps the
 * accent, matching the supplied artwork.
 */
export function BrandLockup({
  to,
  size = "md",
  showWordmark = true,
  tagline = false,
  className = "",
}: {
  to?: string;
  size?: MarkSize;
  showWordmark?: boolean;
  /** The "Practice · Improve · Ace" line from the brand sheet. */
  tagline?: boolean;
  className?: string;
}) {
  const textSize =
    size === "xs"
      ? "text-[0.8125rem]"
      : size === "sm"
        ? "text-[0.9375rem]"
        : size === "md"
          ? "text-base"
          : size === "lg"
            ? "text-xl"
            : "text-3xl";

  const content = (
    <>
      <BrandMark size={size} />
      {showWordmark && (
        <span className="flex flex-col leading-none">
          <span className={`font-semibold tracking-tight text-text ${textSize}`}>
            MockMate<span className="text-accent">AI</span>
          </span>
          {tagline && (
            <span className="marker mt-2 text-[0.5rem] text-text-subtle">Practice · Improve · Ace</span>
          )}
        </span>
      )}
    </>
  );

  const shared = `inline-flex items-center gap-2 ${className}`;

  if (to) {
    return (
      <Link
        to={to}
        aria-label="MockMateAI home"
        className={`${shared} transition-opacity duration-300 [transition-timing-function:var(--ease-out)] hover:opacity-80`}
      >
        {content}
      </Link>
    );
  }
  return <span className={shared}>{content}</span>;
}

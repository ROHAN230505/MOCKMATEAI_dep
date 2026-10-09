import { Link } from "react-router-dom";

/**
 * The MockMateAI wordmark, carried over from the existing brand treatment
 * (graphite/ivory word + accent "AI") and given a mark: two offset speech
 * planes, which is the product in one glyph — a conversation, at an angle.
 *
 * Rendered as inline SVG rather than an image file so it inherits `currentColor`
 * and therefore needs no light/dark asset swap.
 */
export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`relative inline-flex items-center justify-center rounded-[0.55rem] ${className}`}
      aria-hidden="true"
      style={{
        background: "linear-gradient(140deg, var(--grad-a), var(--grad-b))",
        boxShadow: "var(--shadow-glow)",
      }}
    >
      <svg viewBox="0 0 24 24" className="h-[62%] w-[62%]" fill="none" aria-hidden="true">
        <path
          d="M4 7.5A2.5 2.5 0 0 1 6.5 5h8A2.5 2.5 0 0 1 17 7.5v4A2.5 2.5 0 0 1 14.5 14H9l-3.4 2.6A.6.6 0 0 1 4.6 16v-2.2A2.5 2.5 0 0 1 4 12z"
          fill="#fff"
          fillOpacity="0.94"
        />
        <path
          d="M9.5 12.5A2 2 0 0 1 11.5 10.5h6A2 2 0 0 1 19.5 12.5v3a2 2 0 0 1-2 2h-3.6l-2.5 1.9a.5.5 0 0 1-.8-.4v-1.5a2 2 0 0 1-1.1-1.8z"
          fill="#0b0c10"
          fillOpacity="0.32"
        />
      </svg>
    </span>
  );
}

interface LogoProps {
  /** Renders as a link when set; a plain span otherwise (e.g. inside a sidebar header that already links). */
  to?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES = {
  sm: { mark: "h-6 w-6", text: "text-[0.95rem]" },
  md: { mark: "h-8 w-8", text: "text-lg" },
  lg: { mark: "h-10 w-10", text: "text-xl" },
};

export function Logo({ to, size = "md", className = "" }: LogoProps) {
  const s = SIZES[size];
  const content = (
    <>
      <LogoMark className={s.mark} />
      <span className={`font-semibold tracking-tight text-text ${s.text}`}>
        MockMate<span className="text-accent">AI</span>
      </span>
    </>
  );

  const shared = `inline-flex items-center gap-2.5 ${className}`;
  if (to) {
    return (
      <Link to={to} className={`${shared} transition-opacity duration-200 hover:opacity-85`}>
        {content}
      </Link>
    );
  }
  return <span className={shared}>{content}</span>;
}

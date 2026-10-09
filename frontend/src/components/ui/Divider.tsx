import type { ReactNode } from "react";

/** A labelled hairline — the "or continue with email" break on the auth screens. */
export function Divider({ children }: { children?: ReactNode }) {
  if (!children) return <div className="rule-fade my-6" role="separator" />;

  return (
    <div className="my-6 flex items-center gap-3" role="separator">
      <span className="rule-fade flex-1" />
      <span className="text-xs whitespace-nowrap text-text-subtle">{children}</span>
      <span className="rule-fade flex-1" />
    </div>
  );
}

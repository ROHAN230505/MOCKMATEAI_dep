import type { ReactNode } from "react";
import { Card } from "./Card";

/**
 * Loading / empty / error states, shared so every screen fails and waits the
 * same way.
 *
 * Skeletons are shaped like the content they stand in for rather than being a
 * centred spinner: the layout doesn't jump when data lands, and the wait
 * communicates what's coming.
 */

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`animate-sheen block rounded-control bg-surface-raised ${className}`}
    />
  );
}

/** A card-shaped placeholder. `lines` controls how much text is mimicked. */
export function SkeletonCard({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <Card className={className} aria-busy="true">
      <Skeleton className="h-3.5 w-24" />
      <Skeleton className="mt-4 h-7 w-40" />
      <div className="mt-5 flex flex-col gap-2.5">
        {Array.from({ length: lines }).map((_, index) => (
          <Skeleton key={index} className={`h-3 ${index === lines - 1 ? "w-1/2" : "w-full"}`} />
        ))}
      </div>
    </Card>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      {icon && (
        <span
          aria-hidden="true"
          className="mb-1 flex h-12 w-12 items-center justify-center rounded-card border border-border bg-surface-raised text-text-subtle"
        >
          {icon}
        </span>
      )}
      <h2 className="text-base font-semibold text-text">{title}</h2>
      {description && <p className="max-w-sm text-sm leading-relaxed text-text-muted">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </Card>
  );
}

export function ErrorState({ title = "Something went wrong", message, action }: { title?: string; message: string; action?: ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span
        aria-hidden="true"
        className="flex h-11 w-11 items-center justify-center rounded-card border border-danger/30 bg-danger/10 text-danger"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 3h.01M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z" />
        </svg>
      </span>
      <h2 className="text-base font-semibold text-text">{title}</h2>
      <p className="max-w-sm text-sm leading-relaxed text-text-muted">{message}</p>
      {action && <div className="mt-2">{action}</div>}
    </Card>
  );
}

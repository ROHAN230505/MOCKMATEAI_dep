import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
}

/**
 * A custom-drawn checkbox that keeps the native input as the real control —
 * it stays in the tab order, announces correctly, and works with the label
 * association; the visual box is a sibling driven by `peer-checked`. Styling a
 * real input this way is what avoids reimplementing keyboard/AT behaviour.
 */
export function Checkbox({ label, id, className = "", ...rest }: CheckboxProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <label htmlFor={inputId} className="group flex cursor-pointer items-start gap-3 text-sm text-text-muted">
      <span className="relative mt-px flex h-[1.15rem] w-[1.15rem] shrink-0 items-center justify-center">
        <input
          id={inputId}
          type="checkbox"
          className={`peer absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-[0.3rem] border border-border bg-surface-sunken transition-all duration-200 checked:border-accent checked:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent group-hover:border-border-strong ${className}`}
          {...rest}
        />
        <svg
          aria-hidden="true"
          viewBox="0 0 16 16"
          className="pointer-events-none relative h-3 w-3 scale-75 text-accent-contrast opacity-0 transition-all duration-200 peer-checked:scale-100 peer-checked:opacity-100"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m3 8.5 3.2 3.2L13 5" />
        </svg>
      </span>
      <span className="leading-relaxed transition-colors duration-200 group-hover:text-text">{label}</span>
    </label>
  );
}

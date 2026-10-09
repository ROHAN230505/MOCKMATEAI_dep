import type { InputHTMLAttributes, ReactNode } from "react";
import { forwardRef, useId } from "react";
import { FIELD_CLASSES, FIELD_STATE } from "./fieldStyles";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: ReactNode;
  /** Leading adornment (icon or short prefix). Purely visual. */
  adornment?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, adornment, id, className = "", ...rest }, ref) => {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const hintId = `${inputId}-hint`;
    const errorId = `${inputId}-error`;

    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={inputId} className="text-[0.8125rem] font-medium text-text">
          {label}
        </label>
        <div className="relative">
          {adornment && (
            <span
              className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-text-subtle"
              aria-hidden="true"
            >
              {adornment}
            </span>
          )}
          <input
            id={inputId}
            ref={ref}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : hint ? hintId : undefined}
            className={`${FIELD_CLASSES} ${error ? FIELD_STATE.error : FIELD_STATE.normal} ${
              adornment ? "pl-10" : ""
            } ${className}`}
            {...rest}
          />
        </div>
        {error ? (
          <p id={errorId} className="flex items-start gap-1.5 text-[0.8125rem] text-danger">
            <span aria-hidden="true" className="mt-px">
              &#9888;
            </span>
            {error}
          </p>
        ) : (
          hint && (
            <p id={hintId} className="text-xs text-text-muted">
              {hint}
            </p>
          )
        )}
      </div>
    );
  },
);
Input.displayName = "Input";

/** The same chrome for a native select, including the custom chevron. */
export function Select({
  label,
  hint,
  id,
  className = "",
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string; hint?: ReactNode }) {
  const generatedId = useId();
  const selectId = id ?? generatedId;

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={selectId} className="text-[0.8125rem] font-medium text-text">
          {label}
        </label>
      )}
      <div className="relative">
        <select
          id={selectId}
          className={`${FIELD_CLASSES} ${FIELD_STATE.normal} appearance-none pr-10 ${className}`}
          {...rest}
        >
          {children}
        </select>
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="pointer-events-none absolute top-1/2 right-3.5 h-4 w-4 -translate-y-1/2 text-text-subtle"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
        </svg>
      </div>
      {hint && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  );
}

/** The same chrome for a textarea, with an optional character counter. */
export function Textarea({
  label,
  hint,
  counter,
  id,
  className = "",
  ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: string;
  hint?: ReactNode;
  counter?: string;
}) {
  const generatedId = useId();
  const textareaId = id ?? generatedId;

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={textareaId} className="text-[0.8125rem] font-medium text-text">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        className={`${FIELD_CLASSES} ${FIELD_STATE.normal} resize-y leading-relaxed ${className}`}
        {...rest}
      />
      <div className="flex items-start justify-between gap-4">
        {hint ? <p className="text-xs text-text-muted">{hint}</p> : <span />}
        {counter && <p className="tnum shrink-0 text-xs text-text-subtle">{counter}</p>}
      </div>
    </div>
  );
}

/**
 * Shared field chrome, so inputs, selects and textareas are visually identical
 * — including the ones a page hand-rolls rather than importing the component.
 *
 * Kept in its own module (not exported from Input.tsx) so that file exports
 * components only and React Fast Refresh keeps working on it.
 */
export const FIELD_CLASSES =
  "w-full rounded-control border bg-surface px-2.5 py-1.5 text-[0.8125rem] text-text placeholder:text-text-subtle transition-[border-color,box-shadow] duration-150 outline-none";

export const FIELD_STATE = {
  normal:
    "border-border hover:border-border-strong focus:border-accent focus:shadow-[0_0_0_2px_var(--color-accent-soft)]",
  error:
    "border-danger focus:border-danger focus:shadow-[0_0_0_2px_color-mix(in_srgb,var(--color-danger)_16%,transparent)]",
};

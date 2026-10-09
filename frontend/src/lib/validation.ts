// Client-side mirror of the backend's password policy
// (backend/app/core/security.py::validate_password_policy, Section 12.1) —
// server-side is still the source of truth and re-validates on every
// request; this just gives the candidate immediate feedback before a
// round-trip (Section 4.2: "client-side validation first").
const SYMBOLS = /[!@#$%^&*()_+\-=[\]{}|;:'",.<>/?`~\\]/;

export function validatePasswordPolicy(password: string): string[] {
  const errors: string[] = [];
  if (password.length < 8) errors.push("Password must be at least 8 characters long.");
  if (!/\d/.test(password)) errors.push("Password must contain at least one number.");
  if (!SYMBOLS.test(password)) errors.push("Password must contain at least one symbol.");
  return errors;
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

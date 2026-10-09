import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { googleInit } from "../services/authApi";
import { ApiError } from "../lib/apiClient";
import { Spinner } from "./ui/Spinner";

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.616z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.964 10.706A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.038l3.007-2.332z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.962L3.964 7.294C4.672 5.167 6.656 3.58 9 3.58z"
      />
    </svg>
  );
}

/**
 * "Continue with Google" (Section 4.2/4.3): full-width, white background,
 * official-style "G" logo left-aligned. On click, gets the authorization
 * URL from the backend (Section 6.5 step 1) and hands the browser off to
 * Google via a full-page redirect. Shows an inline spinner in place of the
 * logo while that request is in flight, and surfaces a small inline banner
 * (not a full-page error) on failure — matching the spec's failure UX.
 *
 * The white surface is fixed in both themes on purpose: Google's brand
 * guidelines specify the light button treatment, and a recoloured one is both
 * off-guideline and less recognisable at a glance.
 */
export function GoogleButton({ label = "Continue with Google" }: { label?: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefersReducedMotion = useReducedMotion();

  async function handleClick() {
    setError(null);
    setLoading(true);
    try {
      const { authUrl } = await googleInit();
      window.location.href = authUrl;
    } catch (err) {
      setLoading(false);
      setError(
        err instanceof ApiError
          ? "Google sign-in was cancelled or failed. Please try again or use email."
          : "Couldn't reach the server. Please try again.",
      );
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <motion.button
        type="button"
        onClick={handleClick}
        disabled={loading}
        whileHover={loading ? undefined : { y: prefersReducedMotion ? 0 : -1.5 }}
        whileTap={loading ? undefined : { y: 0, scale: prefersReducedMotion ? 1 : 0.99 }}
        transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
        className="flex w-full items-center justify-center gap-3 rounded-control border border-[#dadce0] bg-white px-4 py-2.5 text-sm font-medium text-[#3c4043] shadow-[var(--shadow-sm)] transition-shadow duration-200 hover:shadow-[var(--shadow-md)] disabled:opacity-70"
      >
        {loading ? <Spinner className="text-[#5f6368]" /> : <GoogleLogo />}
        <span>{label}</span>
      </motion.button>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}

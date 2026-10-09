import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "../../components/layout/AuthLayout";
import { Card } from "../../components/ui/Card";
import { Banner } from "../../components/ui/Banner";
import { Spinner } from "../../components/ui/Spinner";
import { googleExchange } from "../../services/authApi";
import { ApiError } from "../../lib/apiClient";
import { useAuthStore } from "../../store/authStore";

// Maps backend error codes (Section 6.5/12.10 collision & failure cases)
// to the exact candidate-facing copy the spec calls for.
const ERROR_MESSAGES: Record<string, string> = {
  google_denied_or_missing_code: "Google sign-in was cancelled or failed. Please try again or use email.",
  invalid_oauth_state: "This sign-in attempt has expired. Please try again.",
  invalid_google_token: "Google sign-in failed. Please try again.",
  google_email_unverified: "Your Google email isn't verified. Please verify it with Google and try again.",
  email_exists_as_password_account:
    "An account with this email already exists. Log in with your password to link Google, or contact support.",
};

/** Lands here after the full-page redirect through Google + our backend callback (Section 6.5). */
export function GoogleComplete() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const urlError = searchParams.get("error");
    if (urlError) {
      setError(ERROR_MESSAGES[urlError] ?? "Google sign-in failed. Please try again or use email.");
      return;
    }

    const ticket = searchParams.get("ticket");
    if (!ticket) {
      setError("Google sign-in failed. Please try again or use email.");
      return;
    }

    const isNewUser = searchParams.get("isNewUser") === "true";
    googleExchange(ticket)
      .then((result) => {
        setSession(result.user, result.accessToken, result.refreshToken);
        navigate(isNewUser ? "/onboarding" : "/dashboard", { replace: true });
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Google sign-in failed. Please try again or use email.");
      });
  }, [searchParams, navigate, setSession]);

  return (
    <AuthLayout>
      <Card tone="glow" className="flex flex-col items-center gap-4 p-7 text-center sm:p-8">
        {error ? (
          <>
            <Banner tone="error">{error}</Banner>
            <div className="flex flex-wrap justify-center gap-4 text-sm">
              <Link to="/login" className="font-medium text-accent hover:underline">
                Back to login
              </Link>
              <Link to="/signup" className="font-medium text-accent hover:underline">
                Sign up with email
              </Link>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-4 py-6">
            <Spinner className="text-2xl text-accent" />
            <p className="text-sm text-text-muted">Finishing Google sign-in…</p>
          </div>
        )}
      </Card>
    </AuthLayout>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "../components/layout/AuthLayout";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Banner } from "../components/ui/Banner";
import { isValidEmail } from "../lib/validation";
import { forgotPassword } from "../services/authApi";
import { ApiError } from "../lib/apiClient";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [devResetToken, setDevResetToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValidEmail(email)) {
      setError("Enter a valid email address.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      // Section 7.1/12.3: always the same outcome regardless of whether the
      // email exists — never branch UI behavior on the response here.
      const result = await forgotPassword(email.trim());
      setSubmitted(true);
      setDevResetToken(result?.devResetToken ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout>
      <Card tone="glow" className="p-7 sm:p-8">
        <h1 className="mb-2 text-xl font-semibold tracking-tight text-text">Reset your password</h1>
        <p className="mb-6 text-sm leading-relaxed text-text-muted">
          Enter the email on your account and we'll send you a link to reset your password.
        </p>

        {error && (
          <div className="mb-4">
            <Banner tone="error">{error}</Banner>
          </div>
        )}

        {submitted ? (
          <div className="flex flex-col gap-4">
            <Banner tone="success">
              If an account exists for that email, we've sent a link to reset your password.
            </Banner>
            {devResetToken && (
              <div className="rounded-control border border-dashed border-accent/40 bg-accent-soft p-4 text-sm">
                <p className="mb-2 flex items-center gap-2 font-medium text-accent">
                  <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-accent" />
                  Development mode
                </p>
                <p className="mb-3 leading-relaxed text-text-muted">
                  No email service is configured yet, so here's the reset link directly:
                </p>
                <Link
                  to={`/reset-password?token=${encodeURIComponent(devResetToken)}`}
                  className="font-medium text-accent hover:underline"
                >
                  Continue to reset password →
                </Link>
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Button type="submit" variant="primary" fullWidth loading={loading}>
              Send Reset Link
            </Button>
          </form>
        )}
      </Card>

      <p className="mt-6 text-center text-sm text-text-muted">
        <Link to="/login" className="font-medium text-accent hover:underline">
          Back to login
        </Link>
      </p>
    </AuthLayout>
  );
}

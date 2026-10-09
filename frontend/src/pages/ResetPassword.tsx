import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "../components/layout/AuthLayout";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Banner } from "../components/ui/Banner";
import { validatePasswordPolicy } from "../lib/validation";
import { resetPassword } from "../services/authApi";
import { ApiError } from "../lib/apiClient";

/** Companion to /forgot-password — the link a candidate lands on from their reset email (or the dev shortcut). */
export function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const issues = validatePasswordPolicy(newPassword);
    if (issues.length > 0) {
      setFieldError(issues.join(" "));
      return;
    }
    if (newPassword !== confirmPassword) {
      setFieldError("Passwords do not match.");
      return;
    }
    setFieldError(null);

    setLoading(true);
    try {
      await resetPassword({ token, newPassword });
      setDone(true);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <AuthLayout>
        <Card tone="glow" className="p-7 sm:p-8">
          <Banner tone="error">This reset link is missing its token. Please request a new one.</Banner>
          <Link
            to="/forgot-password"
            className="mt-4 inline-block text-sm font-medium text-accent hover:underline"
          >
            Request a new reset link
          </Link>
        </Card>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <Card tone="glow" className="p-7 sm:p-8">
        <h1 className="mb-6 text-xl font-semibold tracking-tight text-text">Choose a new password</h1>

        {formError && (
          <div className="mb-4">
            <Banner tone="error">{formError}</Banner>
          </div>
        )}

        {done ? (
          <div className="flex flex-col gap-4">
            <Banner tone="success">Your password has been reset. You can now log in with your new password.</Banner>
            <Button variant="primary" fullWidth onClick={() => navigate("/login")}>
              Go to login
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <Input
              label="New Password"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              error={fieldError ?? undefined}
              hint="At least 8 characters, with upper and lower case, a number and a symbol."
            />
            <Input
              label="Confirm New Password"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
            <Button type="submit" variant="primary" fullWidth loading={loading}>
              Reset Password
            </Button>
          </form>
        )}
      </Card>
    </AuthLayout>
  );
}

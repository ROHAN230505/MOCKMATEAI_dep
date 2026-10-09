import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/layout/AuthLayout";
import { GoogleButton } from "../components/GoogleButton";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Checkbox } from "../components/ui/Checkbox";
import { Button } from "../components/ui/Button";
import { Banner } from "../components/ui/Banner";
import { Divider } from "../components/ui/Divider";
import { isValidEmail, validatePasswordPolicy } from "../lib/validation";
import { signup } from "../services/authApi";
import { ApiError } from "../lib/apiClient";
import { useAuthStore } from "../store/authStore";

export function Signup() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function validate(): boolean {
    const errors: Record<string, string> = {};
    if (name.trim().length === 0) errors.name = "Full name is required.";
    if (!isValidEmail(email)) errors.email = "Enter a valid email address.";
    const passwordIssues = validatePasswordPolicy(password);
    if (passwordIssues.length > 0) errors.password = passwordIssues.join(" ");
    if (password !== confirmPassword) errors.confirmPassword = "Passwords do not match.";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setLoading(true);
    try {
      const result = await signup({ name: name.trim(), email: email.trim(), password });
      setSession(result.user, result.accessToken, result.refreshToken);
      navigate("/onboarding");
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout tagline="Free to start. Your first interview takes ten minutes.">
      <Card tone="glow" className="p-7 sm:p-8">
        <h1 className="mb-6 text-xl font-semibold tracking-tight text-text">Create your account</h1>

        <GoogleButton label="Continue with Google" />

        <Divider>or sign up with email</Divider>

        {formError && (
          <div className="mb-4">
            <Banner tone="error">{formError}</Banner>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          <Input
            label="Full Name"
            autoComplete="name"
            placeholder="Ada Lovelace"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={fieldErrors.name}
          />
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={fieldErrors.email}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={fieldErrors.password}
            hint="At least 8 characters, with upper and lower case, a number and a symbol."
          />
          <Input
            label="Confirm Password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            error={fieldErrors.confirmPassword}
          />
          <Checkbox
            label={
              <>
                I agree to the{" "}
                <a href="#" className="text-accent hover:underline">
                  Terms of Service
                </a>{" "}
                and{" "}
                <a href="#" className="text-accent hover:underline">
                  Privacy Policy
                </a>
              </>
            }
            checked={agreedToTerms}
            onChange={(e) => setAgreedToTerms(e.target.checked)}
          />
          <Button type="submit" variant="primary" fullWidth loading={loading} disabled={!agreedToTerms}>
            Create Account
          </Button>
        </form>
      </Card>

      <p className="mt-6 text-center text-sm text-text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-accent hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}

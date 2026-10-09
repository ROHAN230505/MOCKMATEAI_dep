import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "../components/layout/AuthLayout";
import { GoogleButton } from "../components/GoogleButton";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Banner } from "../components/ui/Banner";
import { Divider } from "../components/ui/Divider";
import { isValidEmail } from "../lib/validation";
import { checkAccountType, login } from "../services/authApi";
import { ApiError } from "../lib/apiClient";
import { useAuthStore } from "../store/authStore";

export function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isGoogleOnlyEmail, setIsGoogleOnlyEmail] = useState(false);

  // Section 4.3: debounced account-type lookup so the "Forgot password?"
  // link can be hidden for a known Google-only account, without turning
  // this into an email-enumeration oracle (the endpoint itself never
  // reveals more than the auth method — see backend Section 12.3).
  useEffect(() => {
    if (!isValidEmail(email)) {
      setIsGoogleOnlyEmail(false);
      return;
    }
    const timeout = setTimeout(async () => {
      try {
        const { authMethod } = await checkAccountType(email.trim());
        setIsGoogleOnlyEmail(authMethod === "google");
      } catch {
        setIsGoogleOnlyEmail(false);
      }
    }, 500);
    return () => clearTimeout(timeout);
  }, [email]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setLoading(true);
    try {
      const result = await login({ email: email.trim(), password });
      setSession(result.user, result.accessToken, result.refreshToken);
      navigate(searchParams.get("redirect") ?? "/dashboard");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout tagline="Welcome back — pick up where you left off.">
      <Card tone="glow" className="p-7 sm:p-8">
        <h1 className="mb-6 text-xl font-semibold tracking-tight text-text">Log in to your account</h1>

        <GoogleButton label="Continue with Google" />

        <Divider>or log in with email</Divider>

        {formError && (
          <div className="mb-4">
            <Banner tone="error">{formError}</Banner>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" variant="primary" fullWidth loading={loading} disabled={!email || !password}>
            Log In
          </Button>
        </form>

        <div className="mt-4 flex justify-center text-sm">
          {!isGoogleOnlyEmail && (
            <Link
              to="/forgot-password"
              className="text-text-muted transition-colors duration-200 hover:text-accent"
            >
              Forgot password?
            </Link>
          )}
        </div>
      </Card>

      <p className="mt-6 text-center text-sm text-text-muted">
        Don't have an account?{" "}
        <Link to="/signup" className="font-medium text-accent hover:underline">
          Sign up
        </Link>
      </p>
    </AuthLayout>
  );
}

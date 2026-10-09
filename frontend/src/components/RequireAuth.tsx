import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

/** Bare auth gate (no sidebar chrome) — used for full-screen authenticated flows like onboarding. */
export function RequireAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ redirect: location.pathname }} />;
  }
  return <Outlet />;
}

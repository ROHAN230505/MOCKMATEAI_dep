import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { AppLayout } from "./layout/AppLayout";

/** Gates every logged-in route (Section 3's sitemap) behind a valid session. */
export function ProtectedRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ redirect: location.pathname }} />;
  }
  return <AppLayout />;
}

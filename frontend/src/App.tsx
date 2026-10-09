import { lazy, Suspense, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { RequireAuth } from "./components/RequireAuth";
import { BrandLoader } from "./components/ui/BrandLoader";
import { BrandIntro } from "./components/brand/BrandIntro";
import { hasSeenIntro } from "./components/brand/introSeen";

// Route-level code-splitting (Section 5.1) — kept as the convention from
// Phase 1 onward since the live-interview pages (Phase 2+) carry
// heavy WebRTC/media code that must not bloat the initial bundle.
const Landing = lazy(() => import("./pages/Landing").then((m) => ({ default: m.Landing })));
const Signup = lazy(() => import("./pages/Signup").then((m) => ({ default: m.Signup })));
const Login = lazy(() => import("./pages/Login").then((m) => ({ default: m.Login })));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword").then((m) => ({ default: m.ForgotPassword })));
const ResetPassword = lazy(() => import("./pages/ResetPassword").then((m) => ({ default: m.ResetPassword })));
const GoogleComplete = lazy(() => import("./pages/auth/GoogleComplete").then((m) => ({ default: m.GoogleComplete })));
const Onboarding = lazy(() => import("./pages/Onboarding").then((m) => ({ default: m.Onboarding })));
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const InterviewSetup = lazy(() => import("./pages/InterviewSetup").then((m) => ({ default: m.InterviewSetup })));
const InterviewPrecheck = lazy(() => import("./pages/InterviewPrecheck").then((m) => ({ default: m.InterviewPrecheck })));
const InterviewLive = lazy(() => import("./pages/InterviewLive").then((m) => ({ default: m.InterviewLive })));
const InterviewProcessing = lazy(() =>
  import("./pages/InterviewProcessing").then((m) => ({ default: m.InterviewProcessing })),
);
const InterviewFeedback = lazy(() =>
  import("./pages/InterviewFeedback").then((m) => ({ default: m.InterviewFeedback })),
);
const InterviewHistory = lazy(() => import("./pages/InterviewHistory").then((m) => ({ default: m.InterviewHistory })));
const Aptitude = lazy(() => import("./pages/Aptitude").then((m) => ({ default: m.Aptitude })));
const Dsa = lazy(() => import("./pages/Dsa").then((m) => ({ default: m.Dsa })));
const Resume = lazy(() => import("./pages/Resume").then((m) => ({ default: m.Resume })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));
const Admin = lazy(() => import("./pages/Admin").then((m) => ({ default: m.Admin })));
const NotFound = lazy(() => import("./pages/NotFound").then((m) => ({ default: m.NotFound })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});


/**
 * The routed tree.
 *
 * **No `AnimatePresence` here, deliberately.** Wrapping `<Routes>` in
 * `AnimatePresence mode="wait"` is a well-known way to blank a page: the
 * incoming route is withheld until every exiting descendant reports its exit
 * complete, and `PageTransition` — which lives *inside* the shell, below the
 * route element — registers with that presence context. When the handshake
 * doesn't resolve, the shell keeps rendering while the routed content stays
 * pinned at `opacity: 0`. Sidebar and header visible, main area empty. That is
 * exactly the failure it caused here.
 *
 * Entrance animation is owned entirely by `PageTransition`'s own
 * `initial`/`animate`, which needs no coordination and cannot deadlock. The cost
 * is losing the exit half of the transition; the benefit is that a screen can
 * never fail to appear.
 *
 * The route table itself is untouched: same paths, same guards, same elements.
 */
function AnimatedRoutes() {
  const location = useLocation();

  return (
      <Routes location={location}>
        <Route path="/" element={<Landing />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/auth/google/complete" element={<GoogleComplete />} />

        <Route element={<RequireAuth />}>
          <Route path="/onboarding" element={<Onboarding />} />
          {/* Full-screen, no sidebar (Section 4.8) — an active interview owns the whole viewport. */}
          <Route path="/interview/live/:sessionId" element={<InterviewLive />} />
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/interview/setup" element={<InterviewSetup />} />
          <Route path="/interview/precheck" element={<InterviewPrecheck />} />
          {/* Section 4.10 then 4.11: processing interstitial, then the report. */}
          <Route path="/interview/processing/:sessionId" element={<InterviewProcessing />} />
          <Route path="/interview/feedback/:sessionId" element={<InterviewFeedback />} />
          <Route path="/interview/history" element={<InterviewHistory />} />
          <Route path="/aptitude" element={<Aptitude />} />
          <Route path="/dsa" element={<Dsa />} />
          <Route path="/resume" element={<Resume />} />
          {/* One component, three real URLs — the sitemap lists all three. */}
          <Route path="/settings" element={<Settings />} />
          <Route path="/settings/:section" element={<Settings />} />
          <Route path="/admin" element={<Admin />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
  );
}

/**
 * The opening title sequence, mounted over the app.
 *
 * Two properties make this safe to put in front of a working product:
 *
 * 1. **It never gates anything.** The routed tree mounts and fetches underneath
 *    it from the first frame, so the intro adds no real latency — by the time it
 *    lifts, the page behind it has already loaded. It is a title card laid over
 *    a running app, not a gate in front of a stalled one.
 * 2. **It only plays on arrival at the front door.** Deep links (a shared report,
 *    a bookmarked dashboard, the OAuth callback) skip it entirely — nobody
 *    following a link to their own data should watch a brand reel first. It's also
 *    once per session, and any key, click, scroll or touch dismisses it.
 */
function IntroGate() {
  const location = useLocation();
  const [done, setDone] = useState(
    () => hasSeenIntro() || location.pathname !== "/",
  );

  return (
    <AnimatePresence>{!done && <BrandIntro onDone={() => setDone(true)} />}</AnimatePresence>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <IntroGate />
        <Suspense fallback={<BrandLoader label="MockMateAI" />}>
          <AnimatedRoutes />
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;

import { AnimatePresence, motion } from "framer-motion";
import { CommandPalette, PALETTE_EVENT } from "./CommandPalette";
import { useRailStore } from "../../store/railStore";
import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { PageTransition } from "../PageTransition";
import { BrandLockup } from "../brand/Brand";
import { ThemeToggle } from "../ThemeToggle";
import { Room } from "../room/Room";
import { Nebula } from "../room/Nebula";

/** Route → the label shown in the header. Keeps the crumb honest without a lookup service. */
const TITLES: { match: (path: string) => boolean; label: string }[] = [
  { match: (p) => p === "/dashboard", label: "Dashboard" },
  { match: (p) => p.startsWith("/interview/setup"), label: "New Interview" },
  { match: (p) => p.startsWith("/interview/precheck"), label: "Device Check" },
  { match: (p) => p.startsWith("/interview/processing"), label: "Generating Report" },
  { match: (p) => p.startsWith("/interview/feedback"), label: "Feedback Report" },
  { match: (p) => p.startsWith("/interview/history"), label: "History" },
  { match: (p) => p.startsWith("/aptitude"), label: "Aptitude" },
  { match: (p) => p.startsWith("/dsa"), label: "DSA Practice" },
  { match: (p) => p.startsWith("/resume"), label: "Resume Analyzer" },
  { match: (p) => p.startsWith("/settings"), label: "Settings" },
];

/**
 * Chrome for every logged-in screen (Section 4.5).
 *
 * A dense application shell: a fixed 240px rail flush to the edge, a 56px header
 * carrying the current screen's name and the global controls, and content on a
 * translucent ground with the galaxy field showing through it. Everything is separated by
 * hairlines rather than by gaps and shadows, which is what lets the working area
 * start immediately below the header instead of after a band of empty space.
 *
 * Below `lg` the rail becomes an overlay drawer, opened from the same header.
 * The drawer closes on route change so a tap never leaves it hanging over the
 * page it just navigated to.
 */
export function AppLayout() {
  const railCollapsed = useRailStore((state) => state.collapsed);
  const railWidth = railCollapsed ? "4rem" : "15rem";
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  const title = TITLES.find((entry) => entry.match(location.pathname))?.label ?? "MockMateAI";

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
    };
  }, [drawerOpen]);

  return (
    <div
      className="relative min-h-screen"
      style={{ "--rail-inset": railWidth } as React.CSSProperties}
    >
      {/* One light, one grain, no motion. Held behind dense data, where anything
          that moved would compete with a number someone is reading. */}
      <Room />
      {/* Section 4: the field runs through the product, but far back. At 0.22
          it is texture in peripheral vision rather than an image; at full
          strength it competes with the figures on a dashboard, and a
          background that wins that fight is a bug however good it looks.

          The live interview screen is not under this layout, so it never gets
          the field at all -- which is the one place a moving backdrop would be
          actively harmful. */}
      <Nebula />

      <CommandPalette />

      {/* Keyboard users shouldn't have to walk the whole nav to reach content. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:bg-accent focus:px-3 focus:py-1.5 focus:text-xs focus:font-medium focus:text-accent-contrast"
      >
        Skip to content
      </a>

      {/* Fixed rail */}
      <aside
        style={{ width: railWidth }}
        className="fixed inset-y-0 left-0 z-30 hidden border-r border-border-strong bg-bg-elevated/80 backdrop-blur-md transition-[width] duration-200 ease-[var(--ease-out)] lg:block"
      >
        <Sidebar />
      </aside>

      {/* Drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            onClick={() => setDrawerOpen(false)}
          >
            <motion.aside
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 500, damping: 42 }}
              className="h-full w-[15rem] border-r border-border-strong bg-bg-elevated"
              onClick={(event) => event.stopPropagation()}
            >
              <Sidebar onNavigate={() => setDrawerOpen(false)} allowCollapse={false} />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <div
        className="relative z-10 transition-[padding] duration-200 ease-[var(--ease-out)] lg:pl-[var(--rail-inset)]"
      >
        {/* Header: one row, 44px, hairline under it. */}
        <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-border-strong bg-bg/75 px-4 backdrop-blur-md sm:px-7">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            className="flex h-8 w-8 items-center justify-center rounded-control text-text-muted transition-colors duration-150 hover:bg-surface-raised hover:text-text lg:hidden"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>

          <span className="lg:hidden">
            <BrandLockup to="/dashboard" size="xs" showWordmark={false} />
          </span>

          <h1 className="text-body font-medium tracking-[-0.012em] text-text">{title}</h1>

          <div className="ml-auto flex items-center gap-2">
            {/* The palette is the fastest way through this product, and a
                shortcut nobody can see is a shortcut nobody uses. Shown as a
                button so it is discoverable, labelled with its key so using
                it once teaches the faster route. */}
            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event(PALETTE_EVENT))}
              className="hidden h-8 items-center gap-2.5 rounded-control border border-border bg-surface/60 px-3 text-tiny text-text-subtle transition-colors duration-150 hover:border-accent/40 hover:bg-accent-soft hover:text-text sm:flex"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <path strokeLinecap="round" d="m20 20-3.5-3.5" />
              </svg>
              Search
              <kbd className="font-mono">⌘K</kbd>
            </button>
            <ThemeToggle />
          </div>
        </header>

        <main id="main-content" className="px-4 py-6 sm:px-7 sm:py-8">
          {/* Keyed by path. Without a key this mounted once for the whole
              session, so its enter animation ran on first load and never
              again -- every subsequent navigation swapped content with no
              transition at all. The key is what makes React treat each route
              as a new element and replay the entrance. */}
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </main>
      </div>
    </div>
  );
}

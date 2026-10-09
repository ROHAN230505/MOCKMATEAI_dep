import { motion } from "framer-motion";
import { NavLink } from "react-router-dom";
import { BrandLockup, BrandMark } from "../brand/Brand";
import { useAuthStore } from "../../store/authStore";
import { useRailStore } from "../../store/railStore";
import { AccountMenu } from "./AccountMenu";
import { sectionsFor, type NavItem } from "./navigation";

/**
 * The navigation rail.
 *
 * Three changes of substance over the version this replaced, none of them
 * decorative:
 *
 *  1. **It collapses.** Icon-only at 4rem, persisted. The rail takes
 *     15rem of every screen permanently, including the DSA workspace where
 *     that width is the difference between a comfortable editor and a cramped
 *     one. Nobody needs to read the word "Dashboard" on their four-hundredth
 *     visit.
 *
 *  2. **Every destination has a keyboard route.** `G` then a letter, shown in
 *     the tooltip and the palette, so the rail teaches its own shortcuts
 *     instead of hiding them in a help page.
 *
 *  3. **The active row carries a tint and a marker.** It started as a marker
 *     alone, on the argument that a filled block at 32px row height eats the
 *     whole slot and the list stops reading as a list. That held while the
 *     rows were 32px and touching; at 36px with a 4px gutter each row has its
 *     own footprint, so a wash one step off the ground reads as *this row is
 *     the one you are on* without becoming a button. The marker stays because
 *     it is the part that moves: it is one shared element animating between
 *     rows, so changing page reads as the indicator travelling rather than one
 *     highlight vanishing and another appearing elsewhere.
 */
function Row({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  return (
    <NavLink
      to={item.to}
      // Opts this navigation into the browser cross-fade defined in
      // index.css. Without it the swap is instant.
      viewTransition
      onClick={onNavigate}
      title={collapsed ? `${item.label}  ·  G then ${item.hint.toUpperCase()}` : undefined}
      className={({ isActive }) =>
        `group relative flex h-9 items-center rounded-control text-small transition-colors duration-150 ${
          collapsed ? "justify-center px-0" : "gap-3 px-2.5"
        } ${
          isActive
            ? "bg-accent-soft font-medium text-text"
            : "text-text-muted hover:bg-surface-raised hover:text-text"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span
              layoutId="rail-active"
              transition={{ type: "spring", stiffness: 620, damping: 46 }}
              className="absolute top-1.5 bottom-1.5 -left-3 w-[2px] rounded-r-full bg-accent"
              aria-hidden="true"
            />
          )}
          <span className={`shrink-0 transition-colors duration-150 ${isActive ? "text-accent" : ""}`}>
            {item.icon}
          </span>
          {!collapsed && <span className="min-w-0 flex-1 truncate">{item.label}</span>}
          {/* The shortcut, revealed on hover rather than always shown. Present
              for discovery, absent from the resting composition. */}
          {!collapsed && (
            <kbd className="shrink-0 font-mono text-micro text-text-subtle opacity-0 transition-opacity duration-150 group-hover:opacity-100">
              g {item.hint}
            </kbd>
          )}
        </>
      )}
    </NavLink>
  );
}

export function Sidebar({
  onNavigate,
  /** Adds the edge border and solid ground used when the rail is flush to the viewport. */
  bordered = false,
  /** The mobile drawer is always full width — collapsing it would leave a rail beside a scrim. */
  allowCollapse = true,
}: {
  onNavigate?: () => void;
  bordered?: boolean;
  allowCollapse?: boolean;
}) {
  const role = useAuthStore((state) => state.user?.role);
  const railCollapsed = useRailStore((state) => state.collapsed);
  const toggle = useRailStore((state) => state.toggle);
  const collapsed = allowCollapse && railCollapsed;
  const sections = sectionsFor(role);

  return (
    <div className={`flex h-full flex-col ${bordered ? "border-r border-border bg-bg-elevated" : ""}`}>
      <div className={`flex h-14 shrink-0 items-center ${collapsed ? "justify-center px-0" : "px-4"}`}>
        {collapsed ? <BrandMark size="xs" /> : <BrandLockup to="/dashboard" size="xs" />}
      </div>

      <div className="hairline mx-3 h-px" />

      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4" aria-label="Main">
        {sections.map((section) => (
          <div key={section.heading} className="mb-6 last:mb-0">
            {/* Collapsed, a heading has no room to be read and a rule says the
                same thing — these are groups, and here is where one ends. */}
            {collapsed ? (
              <div className="hairline mx-1 mb-2 h-px first:hidden" />
            ) : (
              <p className="mb-2 px-2.5 text-micro font-medium tracking-[0.12em] text-text-subtle uppercase">
                {section.heading}
              </p>
            )}
            <ul className="flex flex-col gap-1">
              {section.items.map((item) => (
                <li key={item.to}>
                  <Row item={item} collapsed={collapsed} onNavigate={onNavigate} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="hairline mx-3 h-px" />

      <div className="shrink-0 space-y-1.5 p-3">
        {allowCollapse && (
          <button
            type="button"
            onClick={toggle}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            title={collapsed ? "Expand navigation" : "Collapse navigation"}
            className={`hidden h-9 w-full items-center rounded-control text-small text-text-muted transition-colors duration-150 hover:bg-surface-raised hover:text-text lg:flex ${
              collapsed ? "justify-center px-0" : "gap-3 px-2.5"
            }`}
          >
            <svg
              viewBox="0 0 24 24"
              className={`h-[0.9375rem] w-[0.9375rem] shrink-0 transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 6l-6 6 6 6" />
            </svg>
            {!collapsed && <span className="min-w-0 flex-1 truncate text-left">Collapse</span>}
          </button>
        )}
        <AccountMenu collapsed={collapsed} />
      </div>
    </div>
  );
}

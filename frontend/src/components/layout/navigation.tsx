import type { ReactNode } from "react";
import { Glyph } from "../ui/Glyph";

/**
 * The Section 3 sitemap, as one model.
 *
 * Extracted from the sidebar because it is no longer the only consumer: the
 * command palette navigates the same destinations, and two hand-maintained
 * lists would drift the first time a route was added — the palette silently
 * missing a page is worse than not having one.
 *
 * `hint` is the go-to shortcut: `G` then this key. Keys are chosen to be
 * mnemonic and are asserted unique by `verify-navigation.mjs`, because a
 * duplicate would make one destination permanently unreachable by keyboard
 * while looking perfectly fine on screen.
 */
export interface NavItem {
  to: string;
  label: string;
  /** What this page is for, shown in the palette. */
  description: string;
  hint: string;
  icon: ReactNode;
}

export interface NavSection {
  heading: string;
  items: NavItem[];
}

const size = "h-[1.0625rem] w-[1.0625rem]";

export const NAV_SECTIONS: NavSection[] = [
  {
    heading: "Overview",
    items: [
      {
        to: "/dashboard",
        label: "Dashboard",
        description: "Readiness, recent sessions and what to work on next",
        hint: "d",
        icon: (
          <Glyph className={size}>
            <path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 8h6V4h-6z" />
          </Glyph>
        ),
      },
    ],
  },
  {
    heading: "Practice",
    items: [
      {
        to: "/interview/setup",
        label: "Mock Interview",
        description: "Start a live interview with the AI interviewer",
        hint: "i",
        icon: (
          <Glyph className={size}>
            <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z" />
            <path d="M19 11a7 7 0 0 1-14 0M12 18v3m-4 0h8" />
          </Glyph>
        ),
      },
      {
        to: "/aptitude",
        label: "Aptitude",
        description: "Timed mock tests and topic practice",
        hint: "a",
        icon: (
          <Glyph className={size}>
            <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M3 15v4a2 2 0 0 0 2 2h4m12-6v4a2 2 0 0 1-2 2H9" />
            <path d="M8 12h8M12 8v8" />
          </Glyph>
        ),
      },
      {
        to: "/dsa",
        label: "DSA",
        description: "Coding problems, run and submit in the browser",
        hint: "s",
        icon: (
          <Glyph className={size}>
            <path d="m8 16-4-4 4-4m8 0 4 4-4 4M14 4l-4 16" />
          </Glyph>
        ),
      },
      {
        to: "/resume",
        label: "Resume",
        description: "Analyse a resume against a role",
        hint: "r",
        icon: (
          <Glyph className={size}>
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5M9 13h6M9 17h4" />
          </Glyph>
        ),
      },
    ],
  },
  {
    heading: "Records",
    items: [
      {
        to: "/interview/history",
        label: "History",
        description: "Every past session and its report",
        hint: "h",
        icon: (
          <Glyph className={size}>
            <path d="M12 8v4l3 2" />
            <path d="M3.05 11a9 9 0 1 1 .5 4M3 4v5h5" />
          </Glyph>
        ),
      },
      {
        to: "/settings/profile",
        label: "Settings",
        description: "Profile, privacy and reminders",
        hint: ",",
        icon: (
          <Glyph className={size}>
            <circle cx="12" cy="12" r="2.6" />
            <path d="M19.5 12a7.5 7.5 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7.6 7.6 0 0 0-2-1.2l-.3-2.5h-4l-.3 2.5a7.6 7.6 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7.6 7.6 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7.6 7.6 0 0 0 2 1.2l.3 2.5h4l.3-2.5a7.6 7.6 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.06-.4.1-.8.1-1.2Z" />
          </Glyph>
        ),
      },
    ],
  },
];

/** Section 12.2: hiding this is convenience. The API verifies the role itself. */
export const ADMIN_SECTION: NavSection = {
  heading: "Admin",
  items: [
    {
      to: "/admin",
      label: "Batch analytics",
      description: "Cohort trends, suppressed below five candidates",
      hint: "b",
      icon: (
        <Glyph className={size}>
          <path d="M3 3v18h18M7 15l3-4 3 3 5-7" />
        </Glyph>
      ),
    },
  ],
};

export function sectionsFor(role: string | undefined): NavSection[] {
  return role === "admin" ? [...NAV_SECTIONS, ADMIN_SECTION] : NAV_SECTIONS;
}

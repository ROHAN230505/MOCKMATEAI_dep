import { create } from "zustand";

/**
 * Whether the navigation rail is collapsed to icons.
 *
 * Persisted, because this is a workspace preference rather than a transient UI
 * state: someone who collapses the rail to give the DSA editor more room means
 * it for every session, and re-expanding it on each load would be the app
 * overruling them. Written through a try/catch — private-mode browsers throw on
 * `localStorage` access, and a nav rail is not worth a blank page.
 */
const KEY = "mockmateai.rail";

function stored(): boolean {
  try {
    return localStorage.getItem(KEY) === "collapsed";
  } catch {
    return false;
  }
}

interface RailState {
  collapsed: boolean;
  toggle: () => void;
}

export const useRailStore = create<RailState>((set, get) => ({
  collapsed: stored(),
  toggle: () => {
    const collapsed = !get().collapsed;
    try {
      localStorage.setItem(KEY, collapsed ? "collapsed" : "expanded");
    } catch {
      // Preference is lost on reload; the rail still works this session.
    }
    set({ collapsed });
  },
}));

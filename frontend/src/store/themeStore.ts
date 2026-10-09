// Theme preference: dark / light / follow the OS.
//
// Persisted to localStorage under one key and applied by toggling a single
// `dark` class on <html> — every colour in the app resolves through CSS
// custom properties (see index.css), so nothing else has to know the theme
// exists.
import { create } from "zustand";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "mockmateai.theme";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

/**
 * Dark is the default, not "system".
 *
 * The neural layer is built for it: additive nodes and connection lines bloom
 * against a near-black navy and have almost no headroom over white. Light
 * remains a fully supported theme — the field simply renders fainter there — and
 * once someone picks either one, their choice is what persists.
 */
function readStored(): ThemeMode {
  if (typeof window === "undefined") return "dark";
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "dark";
}

export function resolveTheme(mode: ThemeMode): "light" | "dark" {
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}

function applyToDocument(mode: ThemeMode) {
  if (typeof document === "undefined") return;
  const resolved = resolveTheme(mode);
  document.documentElement.classList.toggle("dark", resolved === "dark");
  // Keeps the browser's own chrome (form controls, scrollbars, autofill) in
  // step with our palette instead of showing light widgets on a dark page.
  document.documentElement.style.colorScheme = resolved;
}

interface ThemeState {
  mode: ThemeMode;
  resolved: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
  /** Re-reads the OS preference; called by the media-query listener. */
  syncFromSystem: () => void;
}

const initialMode = readStored();

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: initialMode,
  resolved: resolveTheme(initialMode),
  setMode: (mode) => {
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, mode);
    applyToDocument(mode);
    set({ mode, resolved: resolveTheme(mode) });
  },
  // The visible switch is binary, so toggling from "system" commits to the
  // opposite of whatever the OS is currently giving them — which is what the
  // user is asking for by reaching for the switch at all.
  toggle: () => get().setMode(resolveTheme(get().mode) === "dark" ? "light" : "dark"),
  syncFromSystem: () => {
    if (get().mode !== "system") return;
    applyToDocument("system");
    set({ resolved: resolveTheme("system") });
  },
}));

/**
 * Applies the stored theme before React renders, so there is no light-mode
 * flash on a dark-mode reload, and wires the OS-preference listener once.
 */
export function initTheme() {
  applyToDocument(initialMode);
  if (typeof window === "undefined") return;
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => useThemeStore.getState().syncFromSystem());
}

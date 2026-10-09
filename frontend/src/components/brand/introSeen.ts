/**
 * Whether the opening title sequence has already played this session.
 *
 * Kept out of `BrandIntro.tsx` so that file exports components only and React
 * Fast Refresh keeps working on it — and so `App` can decide whether to mount
 * the intro at all without importing the animation.
 *
 * `sessionStorage`, not `localStorage`: the intro should play once per visit,
 * not once per lifetime. Someone returning tomorrow gets the open again; someone
 * refreshing mid-task does not.
 */
const STORAGE_KEY = "mockmateai.intro.seen";

export function hasSeenIntro(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    // Private mode blocks storage — treat as seen so the intro can never wedge.
    return true;
  }
}

export function markIntroSeen() {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* Nothing to do — worst case it plays again on the next navigation. */
  }
}

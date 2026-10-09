// Speech-recognition language, persisted.
//
// This exists because the recogniser's language was hardcoded to "en-US", and
// that single line was the largest accuracy problem in the product. The Web
// Speech API does not detect language: it scores the incoming audio against
// the acoustic and language model for whichever locale it was handed. Hand it
// the wrong one and it does not fail or warn — it returns fluent, confident,
// completely different words, which is the worst possible failure mode because
// it looks like a working transcript.
//
// The default is therefore chosen rather than assumed, and the picker lives in
// the device precheck where it can be tested against the user's actual voice
// before an interview depends on it.
import { create } from "zustand";

const STORAGE_KEY = "mockmateai.asr.lang";

/**
 * The English locales Chrome's recogniser has distinct models for, plus the
 * non-English ones it supports well. Restricted to a curated list rather than
 * every BCP-47 tag: an unsupported tag does not error, it silently falls back,
 * which would put us right back at "wrong model, confident nonsense".
 */
export interface AsrLanguage {
  tag: string;
  label: string;
  /** Shown under the label so the choice is about accent, not nationality. */
  hint: string;
}

export const ASR_LANGUAGES: AsrLanguage[] = [
  { tag: "en-IN", label: "English (India)", hint: "Indian English accents" },
  { tag: "en-US", label: "English (US)", hint: "American accents" },
  { tag: "en-GB", label: "English (UK)", hint: "British and Irish accents" },
  { tag: "en-AU", label: "English (Australia)", hint: "Australian and NZ accents" },
  { tag: "en-CA", label: "English (Canada)", hint: "Canadian accents" },
  { tag: "en-ZA", label: "English (South Africa)", hint: "South African accents" },
  { tag: "en-SG", label: "English (Singapore)", hint: "Singaporean and Malaysian accents" },
  { tag: "en-PH", label: "English (Philippines)", hint: "Filipino accents" },
  { tag: "hi-IN", label: "Hindi", hint: "Answer in Hindi" },
];

export const DEFAULT_ASR_LANGUAGE = "en-IN";

/**
 * Picks a starting locale from the browser, and deliberately does NOT simply
 * trust it.
 *
 * `navigator.language` reports the browser's *display* language, which is
 * "en-US" on a large majority of installs worldwide regardless of how the
 * person actually speaks — so trusting it outright reproduces the original bug
 * for exactly the users it hurt most. So an exact match against a locale we
 * list is honoured, an English variant we do not list falls back to the
 * regional default, and anything else lands on the default rather than on the
 * browser's guess.
 */
export function detectAsrLanguage(): string {
  if (typeof navigator === "undefined") return DEFAULT_ASR_LANGUAGE;
  const candidates = [navigator.language, ...(navigator.languages ?? [])].filter(Boolean);
  for (const candidate of candidates) {
    const exact = ASR_LANGUAGES.find((l) => l.tag.toLowerCase() === candidate.toLowerCase());
    // "en-US" is what an unconfigured browser reports, so it is treated as no
    // signal at all rather than as a choice. Any other exact match is real.
    if (exact && exact.tag !== "en-US") return exact.tag;
  }
  return DEFAULT_ASR_LANGUAGE;
}

function readStored(): string {
  if (typeof window === "undefined") return DEFAULT_ASR_LANGUAGE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw && ASR_LANGUAGES.some((l) => l.tag === raw)) return raw;
  } catch {
    // Private mode / blocked storage. A detected default is still better than
    // throwing on the way into an interview.
  }
  return detectAsrLanguage();
}

interface AsrState {
  lang: string;
  /** True until the user picks explicitly, so the UI can say the value was inferred. */
  inferred: boolean;
  setLang: (lang: string) => void;
}

export const useAsrStore = create<AsrState>((set) => ({
  lang: readStored(),
  inferred: (() => {
    if (typeof window === "undefined") return true;
    try {
      return window.localStorage.getItem(STORAGE_KEY) === null;
    } catch {
      return true;
    }
  })(),
  setLang: (lang) => {
    if (!ASR_LANGUAGES.some((l) => l.tag === lang)) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // Not fatal — the choice still applies for this session.
    }
    set({ lang, inferred: false });
  },
}));

// Carries the setup screen's selections to the precheck screen "in session
// state (not URL params, to avoid exposing config in browser history
// unnecessarily)" — Section 4.6. Plain in-memory Zustand store (no
// persistence): a refresh mid-setup is expected to restart the flow.
import { create } from "zustand";
import type { InterviewMode, InterviewType } from "../types/interview";

// Section 4.6: max ~5,000 characters, "character counter shown, server-side
// length-validated". The backend enforces the same bound independently.
export const JOB_DESCRIPTION_MAX_LENGTH = 5000;

interface InterviewSetupState {
  role: string;
  type: InterviewType;
  durationMinutes: number;
  mode: InterviewMode;
  jobDescriptionText: string;
  targetCompanyName: string;
  setSetup: (partial: Partial<Omit<InterviewSetupState, "setSetup">>) => void;
}

export const useInterviewSetupStore = create<InterviewSetupState>((set) => ({
  role: "",
  type: "mixed",
  durationMinutes: 30,
  mode: "voice",
  // Section 4.6's optional custom job targeting. Held here (not in the URL)
  // for the same reason as the rest of the setup state.
  jobDescriptionText: "",
  targetCompanyName: "",
  setSetup: (partial) => set(partial),
}));

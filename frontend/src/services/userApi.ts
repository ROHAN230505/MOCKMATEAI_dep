import { apiRequest } from "../lib/apiClient";
import type { ExperienceLevel, PreferredMode, UserPublic } from "../types/auth";

export function getMe() {
  return apiRequest<UserPublic>("/users/me");
}

export function updatePreferences(input: {
  targetRole?: string;
  experienceLevel?: ExperienceLevel;
  preferredMode?: PreferredMode;
}) {
  return apiRequest<UserPublic>("/users/preferences", { method: "PUT", body: input });
}

export function deleteMe() {
  return apiRequest<null>("/users/me", { method: "DELETE" });
}

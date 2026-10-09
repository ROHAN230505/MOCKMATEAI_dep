// Mirrors backend/app/schemas/user.py::UserPublic and schemas/auth.py — kept
// in one place so every screen/component shares the same shape.

export type AuthProvider = "password" | "google" | "both";
export type UserRole = "candidate" | "admin";
export type ExperienceLevel = "student_fresher" | "1-3_years" | "3+_years";
export type PreferredMode = "voice" | "sign" | "both";

export interface UserPublic {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
  authProvider: AuthProvider;
  role: UserRole;
  targetRole: string | null;
  experienceLevel: ExperienceLevel | null;
  preferredMode: PreferredMode | null;
  createdAt: string;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export interface TokenPairResponse extends TokenPair {
  user: UserPublic;
}

export type AccountAuthMethod = "password" | "google" | "unknown";

// Client/UI state for auth (Section 5.2) — the backend issues bearer
// tokens (not cookies), so the tokens + current user live here, persisted
// to localStorage so a refresh doesn't force a re-login. Server state
// (fetching/mutating through the API) stays in React Query — this store
// only holds what React Query itself can't own.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserPublic } from "../types/auth";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserPublic | null;
  isAuthenticated: boolean;
  setSession: (user: UserPublic, accessToken: string, refreshToken: string) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setUser: (user: UserPublic) => void;
  clearSession: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      setSession: (user, accessToken, refreshToken) =>
        set({ user, accessToken, refreshToken, isAuthenticated: true }),
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setUser: (user) => set({ user }),
      clearSession: () => set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false }),
    }),
    { name: "mockmateai-auth" },
  ),
);

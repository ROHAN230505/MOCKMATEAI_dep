import { apiRequest } from "../lib/apiClient";
import type { AccountAuthMethod, TokenPairResponse } from "../types/auth";

export function signup(input: { name: string; email: string; password: string }) {
  return apiRequest<TokenPairResponse>("/auth/signup", { method: "POST", body: input, auth: false });
}

export function login(input: { email: string; password: string }) {
  return apiRequest<TokenPairResponse>("/auth/login", { method: "POST", body: input, auth: false });
}

export function checkAccountType(email: string) {
  return apiRequest<{ authMethod: AccountAuthMethod }>("/auth/check-account-type", {
    method: "POST",
    body: { email },
    auth: false,
  });
}

export function forgotPassword(email: string) {
  return apiRequest<{ devResetToken?: string } | null>("/auth/forgot-password", {
    method: "POST",
    body: { email },
    auth: false,
  });
}

export function resetPassword(input: { token: string; newPassword: string }) {
  return apiRequest<null>("/auth/reset-password", { method: "POST", body: input, auth: false });
}

export function logout(refreshToken: string) {
  return apiRequest<null>("/auth/logout", { method: "POST", body: { refreshToken }, auth: false });
}

export function googleInit() {
  return apiRequest<{ authUrl: string }>("/auth/google/init", { auth: false });
}

export function googleExchange(ticket: string) {
  return apiRequest<TokenPairResponse>("/auth/google/exchange", { method: "POST", body: { ticket }, auth: false });
}

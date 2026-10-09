import { apiRequest } from "../lib/apiClient";
import type {
  AdminAnalytics,
  NotificationPreferences,
  PrivacyInventory,
  Profile,
} from "../types/settings";

export function getProfile() {
  return apiRequest<Profile>("/users/profile");
}

export function updateProfile(input: { name: string }) {
  return apiRequest<Profile>("/users/profile", { method: "PUT", body: input });
}

export function getNotificationPreferences() {
  return apiRequest<NotificationPreferences>("/users/notifications");
}

export function updateNotificationPreferences(input: NotificationPreferences) {
  return apiRequest<NotificationPreferences>("/users/notifications", { method: "PUT", body: input });
}

export function getPrivacyInventory() {
  return apiRequest<PrivacyInventory>("/users/privacy");
}

export function deleteAccount() {
  return apiRequest<null>("/users/me", { method: "DELETE" });
}

export function logoutAllDevices() {
  return apiRequest<null>("/auth/logout-all-devices", { method: "POST", body: {} });
}

export function getAdminAnalytics() {
  return apiRequest<AdminAnalytics>("/admin/analytics");
}

/** Settings, privacy and admin types (Sections 4.17-4.19, 16). */
import type { ExperienceLevel, PreferredMode } from "./auth";

export interface Profile {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
  authProvider: string;
  /** Derived booleans, never the credentials — enough to know if unlink is allowed. */
  hasPassword: boolean;
  hasGoogle: boolean;
  role: string;
  targetRole: string | null;
  experienceLevel: ExperienceLevel | null;
  preferredMode: PreferredMode | null;
  createdAt: string;
}

export interface NotificationPreferences {
  practiceReminders: boolean;
  weeklySummary: boolean;
  reminderCadenceDays: number;
}

export interface DataCategory {
  key: string;
  label: string;
  count: number;
  detail: string;
}

export interface PrivacyInventory {
  categories: DataCategory[];
  /** Categories never stored at all, each with the reason. */
  neverStored: DataCategory[];
}

export interface AdminAnalytics {
  cohortSize: number;
  suppressed: boolean;
  suppressionReason: string | null;
  engagement: { module: string; users: number; percentage: number }[];
  categoryAverages: { category: string; average: number | null }[];
  weakestCategoryCounts: { category: string; count: number; percentage: number }[];
  aptitudeTopicAccuracy: { topic: string; answered: number; accuracy: number | null }[];
  dsaTopicCompletion: { topic: string; problems: number; solvedByAnyone: number }[];
  notMeasured: { metric: string; reason: string }[];
}

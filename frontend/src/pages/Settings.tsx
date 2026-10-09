import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink, Navigate, useNavigate, useParams } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { Checkbox } from "../components/ui/Checkbox";
import { Input } from "../components/ui/Input";
import { PageHeader } from "../components/ui/PageHeader";
import { ErrorState, SkeletonCard } from "../components/ui/States";
import { ApiError } from "../lib/apiClient";
import { useAuthStore } from "../store/authStore";
import {
  deleteAccount,
  getNotificationPreferences,
  getPrivacyInventory,
  getProfile,
  logoutAllDevices,
  updateNotificationPreferences,
  updateProfile,
} from "../services/settingsApi";

/**
 * Settings (Sections 4.17-4.19).
 *
 * One route with a tab per section rather than three routed pages: the spec's
 * sitemap lists `/settings/profile`, `/settings/privacy` and
 * `/settings/notifications`, and all three are real URLs here — they just share
 * a component, because a tab strip that reloads the whole page on every click
 * would be worse for something people flip between while comparing settings.
 *
 * The privacy tab is the one worth reading. Section 4.17 asks for a list of
 * stored recordings with per-item delete; there are none, so instead of an empty
 * list under a heading that implies otherwise it shows what the account actually
 * holds, counted from real rows, beside an explicit list of what is never stored.
 */

const TABS = [
  { key: "profile", label: "Profile", path: "/settings/profile" },
  { key: "privacy", label: "Privacy & data", path: "/settings/privacy" },
  { key: "notifications", label: "Reminders", path: "/settings/notifications" },
] as const;

function ProfileTab() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [saved, setSaved] = useState(false);

  const profile = useQuery({ queryKey: ["profile"], queryFn: getProfile });

  useEffect(() => {
    if (profile.data && name === "") setName(profile.data.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.data]);

  const save = useMutation({
    mutationFn: () => updateProfile({ name: name.trim() }),
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      window.setTimeout(() => setSaved(false), 3000);
    },
  });

  if (profile.isPending) return <SkeletonCard lines={4} />;
  if (profile.isError || !profile.data) {
    return <ErrorState message="Couldn't load your profile." />;
  }

  const p = profile.data;

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <CardHeader eyebrow="Account" title="Your details" />
        <Input
          label="Name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={255}
        />
        <div className="flex flex-col gap-1">
          <span className="text-[0.8125rem] font-medium text-text">Email</span>
          <span className="text-sm text-text-muted">{p.email}</span>
          {/* Not editable, and the reason is worth stating: changing it would
              need re-verification and would break Google account matching. */}
          <span className="text-xs text-text-subtle">
            Email can't be changed here — it's how your account is identified, including for Google
            sign-in.
          </span>
        </div>
        {save.isError && (
          <Banner tone="error">
            {save.error instanceof ApiError ? save.error.message : "Couldn't save."}
          </Banner>
        )}
        {saved && <Banner tone="success">Saved.</Banner>}
        <Button
          className="self-start"
          loading={save.isPending}
          disabled={!name.trim() || name.trim() === p.name}
          onClick={() => save.mutate()}
        >
          Save changes
        </Button>
      </Card>

      <Card className="flex flex-col gap-3">
        <CardHeader eyebrow="Sign-in" title="How you log in" />
        <div className="flex flex-wrap gap-2">
          {p.hasPassword && <Badge tone="success">Email &amp; password</Badge>}
          {p.hasGoogle && <Badge tone="success">Google</Badge>}
        </div>
        <p className="text-xs leading-relaxed text-text-subtle">
          {p.hasPassword && p.hasGoogle
            ? "Both methods work. You can remove either one, as long as the other stays."
            : p.hasGoogle
              ? "This account signs in with Google. Set a password before removing it — an account must always keep at least one way in."
              : "This account signs in with an email and password."}
        </p>
      </Card>

      <Card className="flex flex-col gap-3">
        <CardHeader eyebrow="Preferences" title="What you're preparing for" />
        <dl className="flex flex-col gap-2 text-sm">
          {[
            ["Target role", p.targetRole ?? "Not set"],
            ["Experience", p.experienceLevel?.replace(/_/g, " ") ?? "Not set"],
            ["Preferred mode", p.preferredMode ?? "Not set"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-4">
              <dt className="text-text-muted">{label}</dt>
              <dd className="text-text">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-text-subtle">
          These come from onboarding and are used to tailor interview questions.
        </p>
      </Card>
    </div>
  );
}

function PrivacyTab() {
  const navigate = useNavigate();
  const clearSession = useAuthStore((s) => s.clearSession);
  const [confirmText, setConfirmText] = useState("");
  const [signedOut, setSignedOut] = useState(false);

  const inventory = useQuery({ queryKey: ["privacyInventory"], queryFn: getPrivacyInventory });

  const signOutEverywhere = useMutation({
    mutationFn: logoutAllDevices,
    onSuccess: () => setSignedOut(true),
  });

  const removeAccount = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      clearSession();
      navigate("/", { replace: true });
    },
  });

  if (inventory.isPending) return <SkeletonCard lines={6} />;
  if (inventory.isError || !inventory.data) {
    return <ErrorState message="Couldn't load your data summary." />;
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader eyebrow="Your data" title="What this account holds" />
        <ul className="mt-4 flex flex-col gap-3">
          {inventory.data.categories.map((row) => (
            <li key={row.key} className="flex items-start justify-between gap-4">
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm text-text">{row.label}</span>
                <span className="text-xs leading-relaxed text-text-subtle">{row.detail}</span>
              </span>
              <span className="tnum shrink-0 text-sm font-semibold text-text">{row.count}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        {/* Stated as its own section rather than left out. "We don't store your
            video" is exactly what someone opens this screen to find out, and an
            absent row says nothing. */}
        <CardHeader eyebrow="Never stored" title="What we don't keep at all" />
        <ul className="mt-4 flex flex-col gap-3">
          {inventory.data.neverStored.map((row) => (
            <li key={row.key} className="flex flex-col gap-0.5">
              <span className="flex items-center gap-2 text-sm text-text">
                {row.label}
                <Badge tone="success">None</Badge>
              </span>
              <span className="text-xs leading-relaxed text-text-subtle">{row.detail}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-col gap-3">
        <CardHeader eyebrow="Sessions" title="Signed-in devices" />
        <p className="text-xs leading-relaxed text-text-subtle">
          Signs you out everywhere by revoking every refresh token. You'll need to log in again on
          this device too.
        </p>
        {signedOut && <Banner tone="success">Signed out of all devices.</Banner>}
        <Button
          variant="secondary"
          className="self-start"
          loading={signOutEverywhere.isPending}
          onClick={() => signOutEverywhere.mutate()}
        >
          Sign out of all devices
        </Button>
      </Card>

      <Card className="flex flex-col gap-3 border-danger/40">
        <CardHeader eyebrow="Irreversible" title="Delete this account" />
        <p className="text-sm leading-relaxed text-text-muted">
          Deletes your account and everything in the list above — interviews, transcripts, feedback,
          aptitude attempts, DSA submissions and resume analyses. It cannot be undone.
        </p>
        {removeAccount.isError && (
          <Banner tone="error">
            {removeAccount.error instanceof ApiError
              ? removeAccount.error.message
              : "Couldn't delete the account."}
          </Banner>
        )}
        {/* Section 4.17: high-friction by design for an irreversible action. */}
        <Input
          label='Type DELETE to confirm'
          value={confirmText}
          onChange={(event) => setConfirmText(event.target.value)}
          placeholder="DELETE"
        />
        <Button
          variant="danger"
          className="self-start"
          loading={removeAccount.isPending}
          disabled={confirmText !== "DELETE"}
          onClick={() => removeAccount.mutate()}
        >
          Delete my account
        </Button>
      </Card>
    </div>
  );
}

function NotificationsTab() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<{
    practiceReminders: boolean;
    weeklySummary: boolean;
    reminderCadenceDays: number;
  } | null>(null);
  const [saved, setSaved] = useState(false);

  const prefs = useQuery({
    queryKey: ["notificationPreferences"],
    queryFn: getNotificationPreferences,
  });

  useEffect(() => {
    if (prefs.data && draft === null) setDraft(prefs.data);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.data]);

  const save = useMutation({
    mutationFn: () => updateNotificationPreferences(draft!),
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["notificationPreferences"] });
      window.setTimeout(() => setSaved(false), 3000);
    },
  });

  if (prefs.isPending || draft === null) return <SkeletonCard lines={4} />;
  if (prefs.isError) return <ErrorState message="Couldn't load your reminder settings." />;

  return (
    <Card className="flex flex-col gap-5">
      <CardHeader eyebrow="Reminders" title="Practice consistency" />

      <Checkbox
        checked={draft.practiceReminders}
        onChange={(event) => setDraft({ ...draft, practiceReminders: event.target.checked })}
        label="Remind me when I haven't practised in a while"
      />
      <Checkbox
        checked={draft.weeklySummary}
        onChange={(event) => setDraft({ ...draft, weeklySummary: event.target.checked })}
        label="Show me a weekly summary of what changed"
      />

      <div className="flex flex-col gap-2">
        <span className="text-[0.8125rem] font-medium text-text">
          Nudge me after {draft.reminderCadenceDays} idle{" "}
          {draft.reminderCadenceDays === 1 ? "day" : "days"}
        </span>
        <input
          type="range"
          min={1}
          max={30}
          value={draft.reminderCadenceDays}
          onChange={(event) =>
            setDraft({ ...draft, reminderCadenceDays: Number(event.target.value) })
          }
          disabled={!draft.practiceReminders}
          className="w-full max-w-sm accent-[var(--color-accent)] disabled:opacity-40"
          aria-label="Idle days before a reminder"
        />
      </div>

      {/* Said plainly rather than implied. Building a settings screen for emails
          that never send would be the fake feature this product exists not to
          ship. */}
      <Banner tone="info" title="Where these appear">
        Reminders show on your dashboard when you next open the app. Email and push delivery need a
        mail service configured, which this build doesn't have — so nothing is sent to your inbox.
      </Banner>

      {saved && <Banner tone="success">Saved.</Banner>}
      <Button className="self-start" loading={save.isPending} onClick={() => save.mutate()}>
        Save preferences
      </Button>
    </Card>
  );
}

export function Settings() {
  const { section } = useParams<{ section?: string }>();
  const active = TABS.find((tab) => tab.key === section);

  // An unknown or missing section lands on Profile rather than a 404: /settings
  // is a reasonable thing to type, and the sidebar links to /settings/profile.
  if (!active) return <Navigate to="/settings/profile" replace />;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Your details, what we store, and when we nudge you."
      />

      <nav className="flex flex-wrap gap-1.5" aria-label="Settings sections">
        {TABS.map((tab) => (
          <NavLink
            key={tab.key}
            to={tab.path}
            className={({ isActive }) =>
              `rounded-pill border px-3.5 py-2 text-xs font-medium transition-colors duration-200 ${
                isActive
                  ? "border-accent/50 bg-accent/12 text-accent"
                  : "border-border text-text-muted hover:border-border-strong hover:text-text"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      {active.key === "profile" && <ProfileTab />}
      {active.key === "privacy" && <PrivacyTab />}
      {active.key === "notifications" && <NotificationsTab />}
    </div>
  );
}

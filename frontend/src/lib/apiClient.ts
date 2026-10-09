// Thin fetch wrapper around the backend's standard envelope
// (`{ success, data?, error? }`, Section 7) — unwraps `data`, throws
// `ApiError` on `success: false` or a network failure, and transparently
// retries once after a silent token refresh on a 401 (Section 12.1's
// short-lived-access-token/rotated-refresh-token design).
import { useAuthStore } from "../store/authStore";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface Envelope<T> {
  success: boolean;
  data?: T;
  error?: { code: string; message: string };
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  auth?: boolean; // attach Authorization header (default true)
  skipRefreshRetry?: boolean; // internal: prevents infinite refresh loops
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefreshAccessToken(): Promise<boolean> {
  const { refreshToken, setTokens, clearSession } = useAuthStore.getState();
  if (!refreshToken) return false;

  // Section 12.1A: a burst of parallel 401s should trigger exactly one
  // refresh call, not one per request — everyone piggybacks on the first.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken }),
        });
        const body = (await res.json()) as Envelope<{ accessToken: string; refreshToken: string }>;
        if (!res.ok || !body.success || !body.data) {
          clearSession();
          return false;
        }
        setTokens(body.data.accessToken, body.data.refreshToken);
        return true;
      } catch {
        clearSession();
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

/**
 * Combines the API's origin (scheme+host, upgraded to ws/wss) with a
 * backend-supplied path (already including the `/api/v1` prefix, e.g.
 * `/api/v1/interviews/:id/live` from `POST /interviews/start` — Section
 * 7.3) plus the access token as a query param, since the browser
 * WebSocket API can't set an Authorization header.
 */
export function buildWsUrl(relativePath: string, accessToken: string): string {
  const origin = new URL(API_BASE_URL);
  const wsProtocol = origin.protocol === "https:" ? "wss:" : "ws:";
  const separator = relativePath.includes("?") ? "&" : "?";
  return `${wsProtocol}//${origin.host}${relativePath}${separator}token=${encodeURIComponent(accessToken)}`;
}

/**
 * Downloads a binary/text file (Section 7.4's transcript and PDF exports).
 *
 * Kept separate from `apiRequest` rather than folded into it: these responses
 * are not the `{ success, data }` envelope, and the only way to send the bearer
 * token with a download is to fetch it and hand the browser a blob URL — a
 * plain `<a href>` can't set an Authorization header.
 *
 * Error responses ARE still the envelope (FastAPI's handlers produce JSON for
 * a 404/409/429), so failures are parsed the same way the rest of the client
 * parses them and surface as a real message instead of a corrupt download.
 */
export async function apiDownload(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const headers: Record<string, string> = {};
  const accessToken = useAuthStore.getState().accessToken;
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method: "GET", headers });
  } catch {
    throw new ApiError(0, "network_error", "Couldn't reach the server. Check your connection and try again.");
  }

  if (response.status === 401) {
    const refreshed = await tryRefreshAccessToken();
    if (refreshed) return apiDownload(path);
  }

  if (!response.ok) {
    let code = "download_failed";
    let message = "Couldn't prepare that download. Please try again.";
    try {
      const envelope = (await response.json()) as Envelope<never>;
      if (envelope.error) {
        code = envelope.error.code;
        message = envelope.error.message;
      }
    } catch {
      /* Not JSON — keep the generic message rather than showing raw bytes. */
    }
    throw new ApiError(response.status, code, message);
  }

  // The backend sets `Content-Disposition: attachment; filename="..."`, which
  // is what makes the saved file findable later instead of being named after
  // the URL path.
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return { blob: await response.blob(), filename: match ? match[1] : null };
}

/** Hands the blob to the browser as a save dialog, then releases the object URL. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, skipRefreshRetry = false } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const accessToken = useAuthStore.getState().accessToken;
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", "Couldn't reach the server. Check your connection and try again.");
  }

  if (response.status === 401 && auth && !skipRefreshRetry) {
    const refreshed = await tryRefreshAccessToken();
    if (refreshed) {
      return apiRequest<T>(path, { ...options, skipRefreshRetry: true });
    }
  }

  if (response.status === 429) {
    const retryAfter = response.headers.get("Retry-After");
    const suffix = retryAfter ? ` Try again in ${retryAfter}s.` : "";
    throw new ApiError(429, "rate_limited", `Too many requests.${suffix}`);
  }

  let envelope: Envelope<T>;
  try {
    envelope = (await response.json()) as Envelope<T>;
  } catch {
    throw new ApiError(response.status, "invalid_response", "Something went wrong. Please try again.");
  }

  if (!envelope.success) {
    const { code = "unknown_error", message = "Something went wrong. Please try again." } = envelope.error ?? {};
    throw new ApiError(response.status, code, message);
  }

  return envelope.data as T;
}

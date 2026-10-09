# Deploying MockMateAI for free

Four services. Netlify alone cannot host this: the backend is a long-running
Python process that holds WebSocket connections, which a static host has no
way to run.

| Piece | Host | Free tier |
|---|---|---|
| Frontend | Netlify | Yes, no card |
| Backend (FastAPI) | Render | Yes, sleeps when idle — see the warning below |
| PostgreSQL | Neon | Yes, no expiry |
| Redis | Upstash | Yes, no card |

**Read this first.** Render's free tier stops the container after 15 minutes
with no traffic, and the next request waits roughly **50 seconds** for it to
start again. Someone opening your link cold sees a spinner for a minute and
concludes the site is broken. If people will be judging this, either warm it up
a few minutes beforehand, point a free uptime pinger at `/health` every 10
minutes, or run it locally instead — localhost has no cold start and the
browser trusts it with the microphone more readily than a brand-new domain.

---

## 1. Database — Neon

1. Sign up at neon.tech, create a project.
2. Copy the connection string.
3. **Change the scheme.** Neon gives you `postgresql://...`; SQLAlchemy needs
   the driver named:

   ```
   postgresql+psycopg://user:password@host/dbname?sslmode=require
   ```

   Keep `?sslmode=require`. Without it the connection is refused.

## 2. Redis — Upstash

1. Sign up at upstash.com, create a Redis database.
2. Copy the **`redis://` TCP URL**, not the REST endpoint. The REST URL looks
   plausible and will not work — rate limiting and live session state both
   speak the Redis protocol.

## 3. JWT keys

The ones in `backend/dev_keys/` are for development. Generate a fresh pair:

```bash
cd backend
./.venv/Scripts/python.exe scripts/generate_dev_keys.py
```

You will paste the **contents** of each `.pem` into Render, not the paths —
there is no `dev_keys/` directory on the server, because keys are secrets and
are not in git. If Render's form flattens the newlines, that is handled; the
loader repairs a collapsed PEM rather than failing with a DER parse error.

## 4. Backend — Render

1. Push this repository to GitHub.
2. On Render: **New → Blueprint**, point it at the repo. It reads `render.yaml`.
3. Set these in the dashboard (all marked `sync: false`, so Render will ask):

   | Variable | Value |
   |---|---|
   | `MOCKMATEAI_DB_URL` | the Neon URL, scheme corrected |
   | `MOCKMATEAI_REDIS_URL` | the Upstash `redis://` URL |
   | `MOCKMATEAI_JWT_PRIVATE_KEY` | contents of `jwt_private.pem` |
   | `MOCKMATEAI_JWT_PUBLIC_KEY` | contents of `jwt_public.pem` |
   | `MOCKMATEAI_LLM_API_KEY` | your Groq key (`gsk_...`) |
   | `MOCKMATEAI_CORS_ALLOWED_ORIGINS` | your Netlify URL — **step 5** |
   | `MOCKMATEAI_FRONTEND_URL` | the same Netlify URL |

   `MOCKMATEAI_REFRESH_TOKEN_SECRET` is generated for you.

4. Deploy. Migrations run on start, so the 52 DSA problems and 50 aptitude
   questions seed themselves.
5. Check `https://your-api.onrender.com/health` returns
   `{"success":true,...}`.

**Chicken and egg:** CORS needs the Netlify URL, which does not exist yet.
Deploy the backend with a placeholder, do step 5, then come back and correct
these two values. The backend restarts in seconds.

## 5. Frontend — Netlify

1. **Add new site → Import an existing project**, pick the same repo.
2. Netlify reads `frontend/netlify.toml`, so the base directory, build command
   and publish directory are already set. Do not override them.
3. Add one environment variable — **Site settings → Environment variables**:

   ```
   VITE_API_BASE_URL = https://your-api.onrender.com/api/v1
   ```

   Include `/api/v1`. The WebSocket URL for the live interview is derived from
   this, so a wrong value breaks the interview as well as every request.

   Vite bakes `VITE_*` in **at build time**. Changing it later needs a
   redeploy, not a restart.

4. Deploy, then go back to Render and set `MOCKMATEAI_CORS_ALLOWED_ORIGINS`
   and `MOCKMATEAI_FRONTEND_URL` to your Netlify URL (no trailing slash).

## 6. Google sign-in (optional)

Email and password work without this. To keep the Google button working:

1. Google Cloud Console → Credentials → your OAuth client.
2. **Authorised JavaScript origins**: add `https://your-site.netlify.app`
3. **Authorised redirect URIs**: add
   `https://your-api.onrender.com/api/v1/auth/google/callback`
4. On Render set `MOCKMATEAI_GOOGLE_CLIENT_ID`,
   `MOCKMATEAI_GOOGLE_CLIENT_SECRET`, and `MOCKMATEAI_OAUTH_REDIRECT_URI` to
   that same callback URL.

The redirect URI must match **character for character**. A mismatch gives
`redirect_uri_mismatch`, which at least names itself clearly.

---

## When it does not work

| Symptom | Cause |
|---|---|
| First load takes ~50s | Render free tier waking up. Expected. |
| Console says CORS blocked | `MOCKMATEAI_CORS_ALLOWED_ORIGINS` does not exactly match the Netlify origin. No trailing slash. |
| Every API call 404s | `VITE_API_BASE_URL` is missing `/api/v1`. |
| Interview connects then drops | Backend asleep or restarting; the client falls back to HTTP polling and keeps working. |
| Login works, refresh logs you out | `MOCKMATEAI_REFRESH_TOKEN_SECRET` changed between deploys. |
| Backend will not start | Usually the DB URL scheme: it must be `postgresql+psycopg://`. |
| Microphone does nothing | HTTPS is required for speech recognition. Netlify and Render are both HTTPS, so check the browser's site permissions. |
| DSA list is empty | Migrations did not run — check the Render deploy log for `alembic upgrade head`. |

## What this costs

Nothing. The limits that actually bite first are Render's sleep, Neon's storage
cap, and your Groq rate limit — none of which charge you, they just stop
serving until the window resets.

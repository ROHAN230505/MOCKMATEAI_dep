# Deploying MockMateAI for free

Everything runs on Render, created in one go from `render.yaml`:

| Piece | Render service | Free tier |
|---|---|---|
| Frontend | Static Site `mockmateai` | Yes, never sleeps |
| Backend (FastAPI) | Web Service `mockmateai-api` | Yes, sleeps when idle — see below |
| PostgreSQL | Postgres `mockmateai-db` | Yes, **but expires** — see below |
| Redis | Key Value `mockmateai-redis` | Yes, not persisted |

**Read this first.**

- **Cold start.** The free API stops after 15 minutes with no traffic, and the
  next request waits roughly **50 seconds**. The frontend still loads at once,
  but sign-in spins until the API is up. Before a demo, open the site a few
  minutes early, or point a free uptime pinger at `/health` every 10 minutes.
- **The free database expires** (Render's pricing page has the current
  window) and its data goes with it. For a project that must outlive that, use
  Neon instead — see *Alternatives* at the end.
- **Free Redis is not persisted.** A restart drops interviews in progress;
  accounts and reports live in Postgres and are unaffected.

---

## 1. Push the code to GitHub

Render deploys from a GitHub repo, so everything you want live must be
committed and pushed. Check `git status` first: anything under
`frontend/public/` is served publicly to anyone with the link.

## 2. JWT keys

The ones in `backend/dev_keys/` are for development. Generate a fresh pair
**outside the repository** -- without a directory argument the script writes to
`dev_keys/` and, since those already exist, does nothing:

```bash
cd backend
./.venv/Scripts/python.exe scripts/generate_dev_keys.py ~/mockmateai-prod-keys
```

You will paste the **contents** of each `.pem` into Render, not the paths —
there is no `dev_keys/` directory on the server, because keys are secrets and
are not in git. If Render's form flattens the newlines, that is handled; the
loader repairs a collapsed PEM rather than failing with a DER parse error.

## 3. Create everything — Render Blueprint

1. Sign up at render.com with GitHub and allow it access to the repo.
2. **New → Blueprint**, pick the repo. Render reads `render.yaml` and lists
   the four services.
3. It asks for the `sync: false` values. Fill in:

   | Variable | Value |
   |---|---|
   | `MOCKMATEAI_JWT_PRIVATE_KEY` | contents of `jwt_private.pem` |
   | `MOCKMATEAI_JWT_PUBLIC_KEY` | contents of `jwt_public.pem` |
   | `MOCKMATEAI_LLM_API_KEY` | your Groq key (`gsk_...`) |
   | `MOCKMATEAI_CORS_ALLOWED_ORIGINS` | `https://mockmateai.onrender.com` (guess — corrected in step 4) |
   | `MOCKMATEAI_FRONTEND_URL` | the same |
   | `VITE_API_BASE_URL` | `https://mockmateai-api.onrender.com/api/v1` (guess — corrected in step 4) |

   Leave the three Google variables empty unless you do step 5.
   The database URL, Redis URL and refresh-token secret are filled in for you.

4. **Apply.** The first deploy takes several minutes: the frontend build
   fetches Pyodide and the MediaPipe models (~50 MB), and the API runs
   migrations on start, which seed the DSA problems and aptitude questions.

## 4. Check the real URLs

Render only gives a service its plain name if nobody else has taken it;
otherwise it adds a suffix (`mockmateai-api-x1y2.onrender.com`). Open each
service in the dashboard and read its actual URL.

1. Open `https://<api-url>/health` — it should return `{"success":true,...}`.
2. If the URLs differ from the guesses in step 3:
   - **API service → Environment**: set `MOCKMATEAI_CORS_ALLOWED_ORIGINS` and
     `MOCKMATEAI_FRONTEND_URL` to the frontend URL. No trailing slash.
   - **Static site → Environment**: set `VITE_API_BASE_URL` to
     `https://<api-url>/api/v1`, **including** `/api/v1`, then
     **Manual Deploy → Clear build cache & deploy**. Vite bakes this in at
     build time, so saving the variable alone changes nothing.
3. Open the frontend URL, sign up, and run one short interview.

## 5. Google sign-in (optional)

Email and password work without this. To keep the Google button working:

1. Google Cloud Console → Credentials → your OAuth client.
2. **Authorised JavaScript origins**: add the frontend URL.
3. **Authorised redirect URIs**: add
   `https://<api-url>/api/v1/auth/google/callback`
4. On the API service set `MOCKMATEAI_GOOGLE_CLIENT_ID`,
   `MOCKMATEAI_GOOGLE_CLIENT_SECRET`, and `MOCKMATEAI_OAUTH_REDIRECT_URI` to
   that same callback URL.

The redirect URI must match **character for character**. A mismatch gives
`redirect_uri_mismatch`, which at least names itself clearly.

---

## When it does not work

| Symptom | Cause |
|---|---|
| Sign-in spins for ~50s | API waking up. Expected on the free tier. |
| Console says CORS blocked | `MOCKMATEAI_CORS_ALLOWED_ORIGINS` does not exactly match the frontend origin. No trailing slash. |
| Every API call 404s | `VITE_API_BASE_URL` is missing `/api/v1`. |
| Changed `VITE_API_BASE_URL`, nothing happened | It is baked in at build time — redeploy the static site. |
| Interview connects then drops | API asleep or restarting; the client falls back to HTTP polling and keeps working. |
| Login works, refresh logs you out | `MOCKMATEAI_REFRESH_TOKEN_SECRET` changed between deploys. |
| Microphone does nothing | Voice needs Chrome or Edge, and the site's microphone permission allowed. |
| DSA list is empty | Migrations did not run — check the API deploy log for `alembic upgrade head`. |
| Everything worked, then the data vanished | The free database expired. |

## Alternatives

- **Postgres on Neon (no expiry).** Delete the `databases:` block from
  `render.yaml`, replace the `fromDatabase` entry with `sync: false`, and paste
  Neon's connection string as `MOCKMATEAI_DB_URL`. Keep `?sslmode=require`;
  the `postgresql://` scheme is fine as given (`config.py` adds the driver).
- **Frontend on Netlify or Vercel.** `frontend/netlify.toml` and
  `frontend/vercel.json` carry the same rewrite and headers. Set the base /
  root directory to `frontend` and `VITE_API_BASE_URL` as above, then delete
  the static site from `render.yaml` so there are not two copies.
- **The API cannot go on Vercel or Netlify**: their functions are
  request/response only and cannot hold the interview's WebSocket open.

## What this costs

Nothing. The limits that bite first are the API's sleep, the database expiry,
and your Groq rate limit — none of which charge you.

# MockMateAI

> Practice like it's real. Walk in ready.

Full product/technical spec: [MASTER_PROMPT.md](./MASTER_PROMPT.md) — the single source of truth for scope, architecture, and every screen's button-level behavior. This README only covers what's needed to run what's been built so far.

## Build status: Phases 1-7 and 9 complete; Phase 8 partial

### Phase 1 — Section 18

- Email/password auth (signup, login, refresh-token rotation, logout, logout-all-devices, forgot/reset password) — Section 7.1
- Google OAuth 2.0 / OIDC ("Continue with Google") — Authorization Code + PKCE, no auto-merge on email collision — Sections 6.5, 7.1A, 12.10
- Progressive account lockout + platform-wide rate limiting — Sections 12.1, 12.1A
- User profile/preferences + full account deletion with cascade — Section 7.2
- The **complete** Section 8 database schema (all 18 tables), via Alembic migrations — later phases build on it without a disruptive migration
- Onboarding wizard (3-step) — Section 4.4
- Dashboard shell wired to real data (zero until later phases populate it) — Section 4.5
- Security baseline: argon2id hashing, RS256 JWTs, security headers, CORS allowlist, standard `{success, data, error}` envelope — Section 12

### Phase 2 — Section 18: the core voice interview loop

- Interview Setup (Section 4.6, minus resume upload / JD-company targeting — see below) → Precheck (Section 4.7) → live interview screen (Section 4.8, voice mode only)
- A **fixed, pre-planned question list** per session (`backend/app/content/question_bank.py`) — deliberately not LLM-generated; Phase 3 adds the LLM Question/Follow-up Engine (Section 9.3) on top of this same pipeline
- Real-time turn-taking: AI "speaks" a question, listens for the answer, advances — including **barge-in** (interrupt the AI mid-question, Section 4.8A) and the **Skip / I Don't Know** button (Section 4.8, button path only — spoken pass-phrase detection needs the LLM, Phase 3)
- Session persistence: every question + transcript answer is stored (Section 8's `interview_questions`/`interview_answers`), session status/timing tracked, full history and per-session detail views
- A Phase-2-honest "session summary" screen at `/interview/feedback/:sessionId` showing the raw transcript, clearly labeled as not-yet-scored — **superseded in Phase 4** by the real report at the same URL, exactly as that page's own docstring anticipated

### Phase 3 — Section 18: add intelligence

- **AI Provider Gateway** (Section 6.7) — provider-agnostic routing with ordered failover, per-provider health tracking (consecutive-failure and >2x-p95-latency degradation), session pinning so a session doesn't flap providers mid-interview, and a failover log line for every switch. Provider order is config, not code.
- **LLM Question/Follow-up Engine** (Section 9.3) — stateful conversation, the full prompt skeleton (ROLE / RULES / SKIP HANDLING / rubric / OUTPUT FORMAT), and provider-enforced strict JSON output rather than a prose request for JSON.
- **Deterministic follow-up guardrails** (Section 10.3) — mandatory below 5, disallowed at 8+, the LLM's judgment in between, a hard 2-consecutive-follow-up cap, and the skip exception that bypasses all of it.
- **Token/cost governance** (Section 9.3A) — per-turn transcript truncation (full transcript still persisted), duration-scaled per-session ceiling, conversation compaction instead of mid-interview failure, a call-count backstop, and per-session accounting into `total_tokens_used`.
- **Prompt-injection resilience** (Section 12.8) — candidate speech fenced as untrusted data, plus server-side score clamping so a model can't award itself an out-of-range score.
- **JD / company targeting is now live** (Section 4.6) — pasted job descriptions and a target company shape questions from question one; the role dropdown becomes optional when a JD is given.
- **Spoken skip phrases** (Section 4.8 / 9.3) — "I don't know", "can we skip this" and close variants produce the same distinct skipped outcome as the Skip button, and are never scored as weak answers.
- **`EVALUATING` turn state** (Sections 10.1, 7.3) — now server-owned and pushed to the client via `turn_state_changed`, so the pause while an answer is evaluated reads as thinking rather than a hang.
- **AI-cost-sensitive quota** (Section 12.1A) — a per-user daily interview-minutes budget in Redis, on top of the existing per-IP request limits.
- **Section 15's AI evaluation set** — a curated strong/weak/vague/skip answer corpus that regression-tests the guardrail logic whenever the prompt changes.

**No database migration was needed for Phase 3** — Section 8's schema already carried `answer_evaluations`, `interview_questions.parent_question_id`, and `interview_sessions.total_tokens_used`, which is exactly why Phase 1 built the whole schema up front.

### Phase 4 — Section 18: the feedback engine

- **Feedback Generation Service** (Section 9.8) — reads the session's questions/answers/`answer_evaluations`, computes the scores deterministically, then asks a provider for the qualitative half only. Section 9.8's split is enforced structurally: the model never receives a score it can change, so the narrative and the number can't disagree.
- **Weighted Readiness Score** (Section 10.2) — content / communication / confidence / body language, with the weights in a real config table (`scoring_weights`) so they can be retuned **without a redeploy**, as the spec requires twice. The dashboard's cross-module Readiness Index now reads the same row.
- **Skip-aware aggregation** (Section 9.8) — skipped questions are excluded from the scoring average entirely, never counted as zero. A session where everything was skipped produces no score rather than a 0.
- **Structured feedback report screen** (Section 4.11) at `/interview/feedback/:sessionId` — overall score + readiness label, per-category breakdown with the weight actually applied, strengths/improvements each citing a question number and a verbatim quote, and the full question-by-question transcript with follow-up and skip markers.
- **Processing interstitial** (Section 4.10) at `/interview/processing/:sessionId` — generation starts server-side the moment the interview ends (both the WebSocket and REST end paths), so a candidate who closes the tab still has a report waiting. The screen polls a real lifecycle status and offers a retry instead of spinning forever.
- **Before & After comparison** (Section 4.11A) — deltas against the most recent earlier attempt, preferring the same target role and flagging the comparison as rough when only a different role is available.
- **Exports** (Section 7.4) — a paginating PDF report (`reportlab`), plus transcript downloads in TXT and JSON. Metered at 20 per hour per user (Section 12.1A's export tier), keyed per account rather than per IP so a shared network doesn't exhaust one user's allowance for everyone.
- **Transcript-derived communication signals** (Section 9.7's text-only subset) — filler-word rate, elaboration, structure markers, quantified answers, and pace when the client supplied real timings.

**Two new migrations**: `scoring_weights` (created and seeded with Section 10.2's published weights) and four lifecycle columns on `feedback_reports` (`generation_status`, `generated_by`, `generation_error`, `created_at`). Both round-trip cleanly and leave no autogenerate drift.

**Measured against Section 18's actual roadmap**, which asks for more in Phase 8 than was built:

| Phase | Section 18 asks for | Status |
|---|---|---|
| 1-7 | Foundation → Interview loop → Intelligence → Feedback → Signals → Sign mode → Aptitude & DSA | Complete |
| 8 | Unified readiness index, trend graphs, **recommendations**, resume analyzer, **recording playback with annotations** | **Partial** — index, trends, recommendations and resume analyzer done; playback not built (nothing is recorded, by design) |
| 9 | Full pass through Section 12's security checklist | **Complete.** 32 items verified live against real Postgres, not asserted from config. One real vulnerability found and fixed — see below |

**Not yet built**, and worth reading before assuming otherwise:

- **`readiness_snapshots` is never written.** The dashboard's trend is computed live in the browser from up to six `GET /feedback/:id` calls, so it plots *interview scores only* — not the composite index across aptitude, DSA and resume that this table has columns for. Filling it needs a scheduled job, which is a deployment decision as much as a code one.
- **Recording playback.** Not a gap: no audio, video or resume file is ever uploaded, by design, so there is nothing to play back. `GET /recordings/:sessionId/audio` says so explicitly.
- ~~`dashboard.weekly_focus` is hardcoded to `[]`~~ — **now built.** See below.
- **The mini code/whiteboard panel** (Section 4.8B, feature 15) — not built.
- **Recording playback** (`/interview/playback/:sessionId`, Sections 4.12/7.5, features 26-27) — not built, and cannot be without recording, which is deliberately absent.
- **Transport fallback and adaptive bandwidth** (Section 6.6, features 52-53) — not built. `transport_mode` is stored but only ever `webrtc_full`.
- **Aptitude mock-test mode** (`/aptitude/test/:testId`, Section 11.1) and company-pattern sets — practice mode only.
- **Server-side `POST /dsa/problems/:id/run`** — running happens client-side instead, so the endpoint does not exist.
- ~~`/settings/*` and `/admin`~~ — **built.** The "Coming Soon" placeholder is gone entirely, along with the stale `Soon` badges the sidebar was still showing on Aptitude, DSA and Resume long after those shipped.
- **Stretch/v2 items never attempted**: multi-language UI, gamification, peer matching, group discussion (features 44, 46-48).

And a caveat that applies to three shipped features: the fingerspelling classifier, the expression thresholds and the ATS heuristic are all verified by construction but **not against real people**. Each says so in its own UI.

### Phase 4's honesty rules (worth reading before you look at a report)

Phase 5 closed the gap this section was written about: all four of Section 10.2's categories are now measurable, and a fully-instrumented voice session scores every one of them. The rules below still govern, because any individual session can still be missing a signal — a muted microphone costs confidence, a covered camera costs body language, and a signed interview has no audio at all by design. Wherever a category has no inputs, the report:

- **Leaves them NULL and says so**, in the API (`measured: false`), on screen (a dashed empty track and a one-line reason), and in the PDF. A neutral 50 would look exactly like a real measurement of poise nobody observed.
- **Renormalizes the weighted formula over the measured categories**, so content/communication's 0.40/0.25 become ~0.62/0.38 of a score that still means "out of 100" — instead of an overall silently capped at 65 for reasons that have nothing to do with the candidate.
- **Refuses invented observations from the model too.** The prompt forbids writing about unmeasured categories, and the server drops any item in one anyway — prompt-level defense alone is never sufficient (Section 12.8).
- **Labels rule-based prose as rule-based.** With no provider configured (the default), the deterministic writer produces the narrative from the same real scores and quotes, and both the report and the PDF state plainly that no model was involved and that it can't judge technical correctness.
- **`GET /recordings/:sessionId/audio` returns a clear `recording_unavailable`** rather than an empty file: ASR runs in the browser and no audio is ever uploaded, so there is genuinely nothing to serve.

Phase 5 was picked up with no change to the scoring code at all — `compute_breakdown` already read `prosody_signals` / `expression_signals` when rows existed, and with all four present the renormalization is a no-op. That contract had a test before the data did.

### Phase 3's LLM provider: deterministic mock by default

`MOCKMATEAI_LLM_PROVIDER_ORDER` defaults to `mock`, which is a **real, deterministic adapter** — not a stub. It scores answers with transcript heuristics approximating Section 9.4's rubric (specificity, STAR structure, quantified outcomes, vague-claim detection), so the entire downstream path runs for real: guardrail bands, follow-up generation, skip handling, evaluation persistence, and token accounting. A fresh clone runs full adaptive interviews with **no API key and no cost**.

Its determinism is also what makes Section 15's evaluation set a genuine regression test — a live LLM's scores aren't reproducible turn to turn, so those assertions would be flaky against a real provider.

What it cannot do is understand meaning: it can't tell a technically wrong answer from a right one, and its follow-ups are templated rather than genuinely contextual. That's the gap a real provider closes:

```bash
# In backend/.env
MOCKMATEAI_LLM_PROVIDER_ORDER=anthropic,mock   # keep mock last as a safety net
MOCKMATEAI_LLM_API_KEY=sk-ant-...
```

then `pip install anthropic` (or `openai`). Both real adapters are written and complete; they lazy-import their SDK so an unconfigured provider never breaks startup. Keeping `mock` last means a provider outage degrades to a working-but-unintelligent interview rather than a dead session.

### Phase 2's ASR/TTS: browser-native, not a cloud provider

This was an explicit scope decision (see the conversation, not just a code comment): Phase 2 uses the browser's built-in **Web Speech API** (`SpeechRecognition` + `speechSynthesis`) instead of a cloud ASR/TTS provider —

- Zero setup cost, works today with no API keys.
- Chrome/Edge only (`SpeechRecognition` isn't implemented in Firefox/Safari) — the precheck screen detects this and blocks starting an interview with a clear message rather than failing silently mid-session.
- Chrome's recognizer sends audio to Google's own speech servers to do the transcription — **not MockMateAI's servers**. The precheck consent screen discloses this plainly. No audio or video is recorded/stored in Phase 2 at all — only the resulting text transcript.
- Because ASR/TTS run entirely client-side, the live WebSocket (`WS /interviews/:sessionId/live`) carries only JSON text/control events, never raw media — there's no WebRTC audio/video pipe to the backend yet. `interview_sessions.transport_mode` records this honestly as `browser_native_speech` (an addition to Section 6.6's transport enum), not one of the real fallback-ladder values.
- Swappable later: `backend/app/services/interview_service.py` and the frontend's `hooks/useSpeechRecognition.ts` / `useSpeechSynthesis.ts` are the two places a real streaming ASR/TTS provider slots in without changing the orchestration logic around them.

## Architecture (Phase 1 + 2 slice)

```
[ React + TS frontend (Vite) ]  --REST-->  [ FastAPI backend ]  -->  [ PostgreSQL ]
        |          |                              |
        |          '--WS (text/control only)-->----'
        |
        | Web Speech API (ASR/TTS, client-side only)
        |
        Zustand (session) + React Query (server state)   -->  [ Redis ] (OAuth pending-auth,
                                                                  login tickets, rate limits)
```

Full target architecture (all services, AI/ML pipeline, WebRTC transport) is in [MASTER_PROMPT.md Section 1.3](./MASTER_PROMPT.md#13-high-level-system-diagram-textual) and built out phase by phase.

## Prerequisites

- Python 3.12+ (Windows: the `py` launcher)
- Node.js 20+
- **Chrome or Edge** — required to actually run a live interview (Web Speech API support); every other screen works in any modern browser
- Docker Desktop (for local PostgreSQL + Redis) — or point `MOCKMATEAI_DB_URL`/`MOCKMATEAI_REDIS_URL` at your own instances

## Setup

### 1. Datastores

```bash
docker compose up -d
```

Starts Postgres on `5432` and Redis on `6379` with the credentials `backend/.env.example` already expects.

### 2. Backend

```bash
cd backend
py -m venv .venv
./.venv/Scripts/pip install -r requirements-dev.txt   # requirements.txt for prod-only

cp .env.example .env                                  # edit if your ports/secrets differ
python scripts/generate_dev_keys.py                   # generates dev_keys/jwt_{private,public}.pem

./.venv/Scripts/python -m alembic upgrade head         # creates all 18 tables

./.venv/Scripts/python -m pytest -q                    # 210 tests, no external services required
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`. Health check: `GET /health`.

Backend tests run against a throwaway SQLite file + `fakeredis` (see `tests/conftest.py`) so they never require Docker to be running — including a full simulated WebSocket interview session via `TestClient.websocket_connect`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env                                  # edit VITE_API_BASE_URL if needed
npm run dev
```

App at `http://localhost:5173`. Open it in **Chrome or Edge** to actually run a mock interview.

### 4. Google OAuth (optional)

The "Continue with Google" button is fully implemented but needs a real Google Cloud OAuth client to work end-to-end:

1. Google Cloud Console → APIs & Services → Credentials → OAuth client ID (Web application).
2. Authorized redirect URI: `http://localhost:8000/api/v1/auth/google/callback`.
3. Consent screen scopes: `openid email profile` only (Section 12.10 — least-scope).
4. Set `MOCKMATEAI_GOOGLE_CLIENT_ID` / `MOCKMATEAI_GOOGLE_CLIENT_SECRET` in `backend/.env`.

Without real credentials, every other auth path (email/password signup/login/reset, onboarding, dashboard, interviews) works normally — only the Google button's round-trip to Google will fail, which surfaces as the spec's own "Google sign-in was cancelled or failed" banner rather than a crash.

## Environment variables

Full reference with comments: [backend/.env.example](./backend/.env.example) and [frontend/.env.example](./frontend/.env.example). Naming follows [Section 20](./MASTER_PROMPT.md#20-branding--naming-reference)'s `MOCKMATEAI_*` convention. Never commit a populated `.env`.

## Notable implementation decisions not spelled out verbatim in the spec

- **Email case-insensitivity**: emails are normalized to lowercase at the application layer instead of a Postgres `citext` column, so the same models work against SQLite in tests and Postgres in production.
- **Timezone-aware timestamps across dialects** (`backend/app/models/types.py::TZDateTime`): Postgres's `TIMESTAMP WITH TIME ZONE` always round-trips timezone-aware, but SQLite always round-trips naive even on the same column definition — a bare `DateTime(timezone=True)` is silently inconsistent across dialects and raises `TypeError` comparing the two. Found by live-testing Phase 2 against real Postgres (the SQLite-only test suite didn't catch it), and fixed the same way as UUIDs already were (`GUID`): a dialect-normalizing `TypeDecorator`. Every timestamp column in the schema uses this now.
- **Enum values, not enum names, in Postgres** (`backend/app/models/types.py::pg_enum`): SQLAlchemy's `Enum` type defaults to storing a Python enum's member *name* (`AuthProvider.PASSWORD` → `'PASSWORD'`) as the native Postgres enum label, not its lowercase `.value` — inconsistent with Section 8's schema, every Pydantic schema, and SQLite. Also found via live Postgres testing; every enum column goes through the `pg_enum()` helper now, which forces `.value`.
- **Google OAuth token handoff**: since `GET /auth/google/callback` is a browser redirect target (not an endpoint the SPA calls directly), the backend hands the browser a short-lived, single-use "ticket" instead of putting tokens in the redirect URL; the frontend's `/auth/google/complete` page exchanges it via `POST /auth/google/exchange`. See the docstring in `backend/app/services/google_oauth_service.py`.
- **`POST /auth/google/link`**: implemented as `/auth/google/link/init` (step-up password re-confirmation while still authenticated) + the shared callback completing the link — a redirect flow can't carry a Bearer token, so the step-up check has to happen before the redirect, not after.
- **Password reset tokens**: two nullable columns on `users` (`reset_token_hash`, `reset_token_expires_at`) rather than a new table — not itemized in Section 8 but required to implement Section 7.1's reset flow.
- **Interview questions are a topic backbone, not a script (Phase 3)**: the static bank (`backend/app/content/question_bank.py`) survives, but now seeds *topics* the LLM turns into actual utterances. Consequently `interview_questions.question_text` is deliberately overloaded — it holds the planned topic seed while `asked_at IS NULL`, and the real utterance the candidate heard once asked (which Section 4.8A requires). That works because only unasked rows are ever read as seeds, and it avoids a second column plus a migration for data that's never needed after delivery.
- **Follow-ups point at their root question, not their immediate parent**: Section 8 describes `parent_question_id` as a self-ref without mandating a shape. Root-pointing makes Section 10.3's cap ("no more than 2 consecutive follow-ups on the same original question") a single-pass count, and chain order isn't lost since `sequence_order` still records it.
- **Resume upload (Section 4.6) is still not shown**: JD/company went live in Phase 3 because the engine now reads them, but nothing consumes a resume until the Resume Analyzer (Phase 8), so that input stays hidden rather than doing nothing silently.
- **Live WebSocket auth**: the access token travels as a `?token=` query param (`ws://.../live?token=...`) since the browser `WebSocket` API can't set an `Authorization` header. Validated once at connection handshake, same trust boundary as a normal request's Bearer token.
- **Split state-machine ownership (Phase 3)**: ASR/TTS still run in the browser, so `useInterviewOrchestrator` owns AI_SPEAKING/LISTENING — the speech APIs are the only thing that knows the true state there. Evaluation moved server-side, so the backend now owns Section 10.1's `EVALUATING` and announces it via `turn_state_changed`. The split is by *who can actually observe each state*, and the client deliberately adopts only `EVALUATING` from the server rather than every state, so a server message can't unmute the mic while TTS is still audible.
- **The WS protocol is extended additively**: every Phase 2 event name and payload field still works. `question_asked` gained `questionType` / `isFollowup` / `plannedRemaining`, and `turn_state_changed` / `followup_triggered` are new — so a Phase 2 client keeps functioning against a Phase 3 server.
- **Skip detection requires more than a matching phrase**: "I don't know the exact syntax **but** the approach is to cache it in Redis" is a candidate qualifying an answer, not passing on it. A pass phrase followed by a contrastive conjunction and real content is therefore not treated as a skip — otherwise a real answer gets silently discarded, denying the candidate both a score and a follow-up. (Section 15's evaluation set caught this.)
- **Token counting uses a shared ~4-chars-per-token estimate**, not a real tokenizer: exact counts are provider-specific (and change between model generations), so one consistently conservative estimate is more useful for enforcing a *budget* than a number that's exact for one provider and wrong for the others. Actual billed usage always comes from the provider response and is what lands in `total_tokens_used`.
- **The AI quota fails open**: a Redis outage lets interviews proceed. It's a cost-control limit, not a security boundary — and the security-relevant limits (Section 12.1A's strict auth tier) are enforced separately.
- **`llm_provider_used` stays null for the mock and for degraded mode**: Section 8's enum only knows real vendors, and inventing a value for "mock" or "no provider" would make cost analytics claim a vendor served a session that none did.
- **Scoring weights live in a table, not an env var (Phase 4)**: Section 10.2 says "store in a config table, not hardcoded ... so they can be tuned later without a redeploy". An env var doesn't satisfy that — changing one needs a process restart, which is a redeploy in every deployment model this targets. `scoring_weights` keeps one active row so "which weights produced this score" stays answerable; a retune inserts a new active row rather than mutating history.
- **The mock adapter deliberately can't write reports**: it implements interview turns but not `complete_json`, so Section 9.8's call falls through to the next provider and then to the deterministic writer. Faking report prose from a rule engine would produce writing that reads like analysis without being any. The gateway skips it without marking it unhealthy — "doesn't do this" isn't a failure, and counting it would degrade a provider for the turns it does serve.
- **The gateway gained a second call shape, not a bypass**: Section 6.7 makes it "the single entry point for every LLM call", so feedback generation goes through `gateway.complete_json()` and inherits the same failover, health tracking, session pinning and token accounting an interview turn gets. Both entry points share one dispatch loop so their behaviour can't drift apart.
- **The dashboard index zero-fills where the report renormalizes**: a missing `confidence_score` means *this build can't measure poise yet*, so renormalizing avoids penalising the candidate for our gap. A missing `aptitude_avg` means *they haven't taken an aptitude test*, which is a real readiness gap and should pull the index down. Same formula shape, deliberately different treatment of absence — documented at both call sites.
- **A deterministic report is a success, not a failure**: `generation_error` is recorded on a READY report when the provider was unavailable (useful for Section 13's monitoring), but the status endpoint only exposes `error` when status is `failed` — otherwise the processing screen would cry wolf over a report that generated fine.
- **Downloads go through `fetch` + a blob URL, not a plain link**: a bare `<a href>` can't send the bearer token, and these endpoints are authorized per session (Section 12.2). Error responses are still the standard envelope, so a 429 surfaces as its real message instead of a corrupt file.

## Project structure

```
backend/
  app/
    core/        # security (hashing/JWT), rate limiting, middleware, response envelope, timeutils
    models/      # SQLAlchemy models — the complete Section 8 schema
    schemas/     # Pydantic request/response models (camelCase on the wire)
    services/    # business logic, framework-independent
    routers/     # FastAPI route definitions (REST + the interview WebSocket)
    content/     # static content (the question-topic bank)
    services/feedback/   # Phase 4: scoring, prompts, narrative, generator, exports, comparison
  alembic/       # migrations: initial schema, Phase 2's enums, Phase 4's scoring/report columns
  tests/         # 210 tests, SQLite + fakeredis, no external services needed
frontend/
  src/
    pages/       # one file per route
    components/  # ui/ primitives, layout/ chrome, feature components
    hooks/       # speech recognition/synthesis, mic level, interview orchestrator
    services/    # typed API client functions
    store/       # Zustand (client/session state)
    lib/         # fetch wrapper, WS URL builder, client-side validation
```

## Phase 5 — Multimodal signals (Section 9.7)

Both halves are measured in the browser and never leave it. What crosses the network is aggregates: two floats for prosody, three scores for expression.

- **Voice prosody** — pitch variance by NSDF periodicity analysis and pause patterns by voice-activity detection (`frontend/src/lib/prosodyDsp.ts`), with speaking pace and filler count derived *server-side* from the transcript so there is one source of truth. Samples under 12 seconds of voiced audio are discarded rather than trusted.
- **Expression** — eye contact, smile frequency and posture flags from MediaPipe's Face Landmarker (`frontend/src/lib/expressionMetrics.ts`). Head pose is derived from landmark geometry rather than MediaPipe's transformation matrix specifically so it can be validated against known rotations.
- **Self-hosted, pinned, no CDN.** `@mediapipe/tasks-vision` is pinned to an exact version; `frontend/scripts/setup-mediapipe.mjs` copies the WASM out of `node_modules` and fetches the model once against a pinned SHA-256. Nothing is fetched from a third-party host at runtime.
- **Verifiable maths.** There is no frontend test runner, so the pure logic is checked by `npm run verify:prosody` and `npm run verify:expression`, which import the TypeScript directly under Node's type stripping. Both caught real bugs — the first pitch detector reported 75Hz for a 150Hz vowel.

## Phase 6 — Sign-language mode (Section 18)

`mode: "sign"` is now a first-class path through the same engine, the same question sequencing, the same follow-up logic and the same report. What changes is only the speech layer: no TTS, no recogniser, no microphone requested at all. Questions appear as text and answers are typed and submitted explicitly, so nothing is captured until the candidate is ready.

### Hand recognition

Two capabilities, from one self-hosted MediaPipe bundle (`gesture_recognizer.task`, pinned by digest like everything else). They are different in kind and the UI says which is which:

- **Control gestures** — Google's *trained* seven-gesture classifier. Hold ✋ to submit an answer, 👎 to skip. A deliberate 1.2s hold with a visible arming ring, because an accidental submit costs a turn.
- **Fingerspelling** — a *geometric* classifier (`frontend/src/lib/fingerspelling.ts`) over the same bundle's hand landmarks. It measures per-finger straightness and thumb placement and matches them against written descriptions of each ASL letter handshape. Hand-authored rules, not a trained model.

**It reads 12 letters** — A B C D F I L O U V W Y — and deliberately declines the other 14. Each exclusion is because guessing would produce *wrong* letters rather than none: E/M/N/S/T are one fist differing only by a thumb the camera cannot see; G/H/P/Q/K share a handshape with a covered letter and differ only by orientation or thumb insertion; R/X sit inside landmark noise of U/D; J/Z are movements, not handshapes. All 14 reasons are listed in the UI, not buried.

**The two modes are mutually exclusive**, because the trained gestures collide with the letter shapes — ☝️ is D, ✌️ is V, ✋ is close to B. Running both would fire a control action on every V the candidate spelled.

**The honest limitation.** The thresholds come from the geometry of each handshape, not from recordings of signers, and there is no labelled dataset in this project to measure them against. `npm run verify:fingerspelling` proves the code implements the rules on hands built from anatomical joint angles; it cannot prove the rules match how real people sign, and no accuracy figure is claimed. It earned its keep anyway — it caught five real defects, including an unweighted score that read an `L` as a `V` and a "straight finger" band loose enough to make `F` outrank `O`.

That limitation is also why nothing here is authoritative: letters append into a text field that stays fully editable, after a hold, with the pending letter and its confidence on screen before it lands. **A misread costs a keystroke, never an answer.**

### Sharing one thread between two vision models

Sign mode is the heaviest screen in the product: the Face Landmarker (body-language signals) and the Gesture Recognizer (hands) both run over the same camera feed on the same thread, alongside React, the WebSocket and a WebGL background.

Rather than trust a frame rate chosen on a developer's machine, both are paced by `frontend/src/lib/frameBudget.ts`, which **measures what inference actually costs on the device it is running on** and reduces the rate until it fits. Two things it fixes:

- **Two fixed timers drift into alignment and stay there**, so both models land in the same animation frame and the interview stutters at their combined cost. The hand recogniser is given a half-interval phase offset so the two interleave deliberately. `npm run verify:framebudget` checks that over 900 frames they never share one.
- **Load allowances add up.** Two models each permitted half the thread can between them claim all of it, and neither will ever consider itself the problem. Each is capped at 0.35 in sign mode instead of 0.5, holding their combined draw near 70%.

Backing off costs almost nothing: eye contact is a proportion over minutes, posture episodes last seconds, and a fingerspelled letter is held for 600ms — which still gets five samples at the 8fps this may fall to. The interview not stuttering matters more. It will not go below 5fps, and it recovers more slowly than it backs off so one cheap frame cannot undo a reduction a sustained cost earned.

**What it still does not claim.** It is not sign-language translation. ASL has its own grammar and is not fingerspelled English; continuous sign translation is an open research problem. This spells words letter by letter, and the typed answer is what gets submitted.

**The rubric had to change to stay fair.** Two communication terms measure *how words sounded* and mean nothing in a signed answer:

- **Filler words.** An English filler regex finds nothing in a signed answer, so the old formula handed every signing candidate the full "clean speech" bonus for fluency nobody assessed.
- **Speaking pace.** Words-per-minute is not a signing rate, so the 110-160 band judged them against a unit that does not apply.

Both are dropped for a signed session and the surviving terms are scaled up to cover their range — the same renormalization Section 10.2 uses for whole categories, one level down. Without it a flawless signed session would cap near 95 while a flawless spoken one reached 100, so the two scores would not mean the same thing. For voice the factor is exactly `1.0`, and `tests/test_sign_mode.py` pins that against an independent re-implementation of the old formula across 20 fixtures, because a phase that quietly moved every existing candidate's score would be worse than one that never shipped.

Confidence reports as **not applicable** rather than **not recorded** for a signed session, in the API, on screen and in the PDF. "Needs voice-tone analysis, which this session didn't record" would invite a signing candidate to go and fix a deliberate design decision.

## Phase 7 — Aptitude & DSA (Section 18)

Both modules light up dashboard tiles that have existed since Phase 1 and been returning zero ever since — `dashboard_service` already averaged `AptitudeAttempt.score` and counted distinct passed `DSASubmission` problems.

### Aptitude

32 curated questions across all four topics, every answer carrying its working so a reviewer can check it without re-deriving. `correct_option_index` never leaves the server before submission — pinned against the raw response body, not the parsed shape.

**Score is stored as a percentage, not a correct-count.** The dashboard averages that column straight into a 0-100 readiness index, so a raw count would make the average incoherent across attempts of different lengths; `total_questions` preserves the denominator.

**Options are shuffled deterministically at seed time.** Written by hand, the correct answer landed at index 1 or 2 in 30 of 32 questions and never at 0 or 3 among the numeric ones — always picking B would have scored 59% on a test meant to measure aptitude. The shuffle is SHA-512-seeded from the question text so it is stable across runs, which matters because `selected_option_index` is persisted as an index.

### DSA

8 problems, 54 test cases, **all verified by executing a reference solution against them** rather than by anyone reading them and agreeing. That caught two wrong expected values during authoring — both would have failed a *correct* candidate solution with no way for them to see why. References live server-side only and are stripped from every row.

**Solutions run in the candidate's own browser** via self-hosted Pyodide (pinned `314.0.6`, copied out of `node_modules`, no network at setup and none at runtime — `packageBaseUrl` is pinned too so the library's jsdelivr default is unreachable). No untrusted code executes on the server, which removes the entire sandboxing surface.

The acknowledged cost, stated in the UI rather than hidden: the hidden test cases must reach the client to be run against, so a candidate can read them from devtools. Fine for practice; it would not be for an assessment with stakes.

**Runaway loops are stopped by an instruction budget, not a timer.** Pyodide runs on the main thread, so a `while True:` cannot be interrupted by any JavaScript timer — it would hang the tab. The candidate's function runs under a Python `sys.settrace` counter that raises after 2M lines, making the cutoff deterministic rather than dependent on machine speed.

**Hidden failures stay opaque.** A sample failure shows arguments and both values (they are already in the statement); a hidden one says only "wrong answer" — otherwise "your solution is wrong" becomes "here is the input to special-case".

Hints escalate through four levels via the AI gateway, with a deterministic ladder fallback, and are checked for containing code before being shown — a model that answers outright destroys the exercise, and prompt-level defence alone is never sufficient.

### A latent bug this phase exposed

`func.avg()` over an Integer column returns `decimal.Decimal` on Postgres and `float` on SQLite, and the dashboard multiplies that average by a float weight. The `TypeError` had been reachable since Phase 1 but was invisible twice over: `aptitude_attempts` was empty so the value was always NULL and the multiplication never ran, and the test suite runs on SQLite. It surfaced the first time a real attempt was scored against real Postgres — the third cross-dialect bug in this project found that way.

## Phase 8 — Resume analyzer (Section 18)

The last of Section 18's modules, and the last dashboard tile to light up — `dashboard_service` has read `resume_analyses.ats_score` since Phase 1.

### The file never leaves the browser

A resume is the most PII-dense document a candidate owns: legal name, home address, phone number, email, entire employment history. Every other media pipeline here already keeps the raw artifact client-side — audio in Phase 2, video in Phase 5B, candidate code in Phase 7 — and this was the last document that should break that pattern.

So pdf.js (pinned, worker served from our own origin, no CDN) extracts text in the browser and the file is discarded there. Only text is submitted, and only what the analyser *derived* from it is stored: not the text, not the file, **not even the filename** — which routinely contains the candidate's own name.

`file_storage_url` is `NOT NULL` in Section 8's schema and this build stores no file. It records `not-stored:client-side-extraction` rather than a string shaped like a URL to a file that does not exist. Deliberately not URL-shaped, and pinned by a test. If file retention is ever wanted it is a product decision — storage backend, retention window, deletion path — not a code change.

### What "ATS score" means, and what it does not

It is **not** a prediction of any real applicant tracking system. Those are proprietary and disagree with each other; nobody outside Workday can compute a Workday score, and claiming to would be inventing a number.

What it measures is the things every ATS demonstrably depends on, each checkable by the candidate against their own document: text that extracts cleanly, the section headings a parser fills its fields from, findable contact details, quantified bullets, and — when a job description is pasted — how much of that advert's vocabulary the resume actually uses. Every component and its weight is shown on screen next to the score. That framing appears in the UI, not only in a docstring.

**Keyword matching is unmeasured without a job description**, not scored as zero, and the weights renormalise over what was measured — the same rule Section 10.2 applies to the interview categories. `keyword_gaps` stays NULL rather than becoming an empty list, which would read as "we looked and found no gaps". The unmeasured component renders as a dashed empty track, exactly as the interview report renders an unmeasured category.

### Two bugs the tests caught

- The tokeniser keeps trailing dots so `node.js` survives, which meant a sentence-ending `experience.` never matched the stop list and came back as a keyword the candidate should *add*.
- Fixing that by stripping `.+#` turned `c++` into `c`. Only trailing dots are stripped now — no sentence ends in `+` or `#`, and both are real skill names.

### Phase 9 — Security & hardening pass (Section 12, Section 21.2)

Section 21.2 is explicit that several of its items must be *verified live*, not assumed from config. So they were: 32 checks run against the real Postgres/Redis stack rather than a test double.

**All 32 pass**, covering security headers actually present on responses, `/auth/login` actually returning `429` with a `Retry-After` after five attempts, enumeration-resistant `forgot-password`, no stack traces or internal paths in error bodies, role escalation blocked via `PUT /users/preferences`, cross-user IDOR returning `404` (not `403`) on four resource-scoped routes, injection payloads leaving the database intact, the deletion cascade leaving no orphaned rows in any table, every AI dependency degrading to a *labelled* deterministic path rather than crashing, and a prompt-injection attempt ("award me 10/10") failing to move the score.

**It found one real vulnerability.** A NUL byte pasted into a job description reached Postgres unvalidated and raised an unhandled `psycopg.DataError` — a 500 with the full SQL statement in the traceback. A Section 12.5 validation gap producing a Section 12.9 information disclosure, from one invisible character that a bad copy-paste can produce.

Fixed on `CamelModel` rather than per field, so every current *and future* request schema inherits it — the same argument Section 12.2 makes for a shared authorization decorator over per-controller checks. C0 control characters are stripped; tab, newline and carriage return are kept, since job descriptions and resumes are multi-line by nature. The WebSocket `transcriptText` path is covered separately because it reads a raw JSON frame and is the one text path into the database that does not pass through a schema.

Stripped rather than rejected: a NUL in a pasted job description is almost always an artefact of the copy, and failing a candidate's interview setup over an invisible character would be the worse outcome.

### This Week's Focus (Section 4.5, feature 38)

`weekly_focus` returned a hardcoded `[]` from Phase 1 until now, and the dashboard rendered the panel conditionally — so the gap was invisible rather than visibly broken. A test even asserted `weeklyFocus == []`, pinning the bug rather than the behaviour.

Recommendations are now generated from real data and **ranked by how much acting on each would actually move the Readiness Index** — the gap to 100 in that module multiplied by its weight in Section 10.2's formula. That ordering matters because it differs from ranking by raw score: a candidate at 40% on aptitude (weight 0.20) and one who has never analysed a resume (weight 0.10) look very different by score and nearly identical by index impact, and the second framing is the one that answers "what should I do this week".

The weights come from the same config table the index itself reads, so retuning them reprioritises the advice automatically rather than letting score and guidance drift apart. Every chip carries the measurement behind it, and the projected gain, and a Start button routing to the module — the string-only shape it had before had nowhere to put a route, which is why it could not have satisfied the spec.

Nothing is suggested that was not measured: an unmeasured interview category is never named as the weakest, a topic with fewer than four answered questions is not called a weakness, and a module already scoring above 80 is left alone rather than padded in to fill three slots.

## Next

The eight phases of Section 18's roadmap are built. What remains is listed under **Not yet built** above — chiefly the `readiness_snapshots` rollup job, the admin dashboard, and `/settings/profile`.

Note that this README is the only surviving description of the roadmap: `MASTER_PROMPT.md` was supplied as a chat attachment and is not in the repository, so "complete against the spec" is not something this repo can verify. What it can show is the section references throughout the code and the tests that pin each one.

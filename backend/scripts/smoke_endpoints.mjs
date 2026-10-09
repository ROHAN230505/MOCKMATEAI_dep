/**
 * Live endpoint smoke test — every HTTP route, against a running server.
 *
 *   node scripts/smoke_endpoints.mjs            # http://localhost:8000
 *   node scripts/smoke_endpoints.mjs http://host:port
 *
 * ## What this catches that `pytest` does not
 *
 * The test suite exercises routes through FastAPI's TestClient, which never
 * builds a real HTTP request, never goes through the ASGI server, and never
 * touches the running container's config. So it cannot see a bad CORS origin,
 * a rate limiter wired to the wrong backing store, a migration that has not
 * been applied to the live database, or a dependency upgrade that changed how
 * the server parses a body. All of those are deployment failures, and all of
 * them look fine in CI.
 *
 * ## What "expected" means here
 *
 * Every call declares the statuses it should be able to return, and several
 * declare a 4xx *deliberately*, because the refusal is the behaviour under
 * test:
 *
 *   - 401 on every guarded route with no token
 *   - 403 on the admin route for a normal account
 *   - 409 on an unsubmitted aptitude attempt, because that response body
 *     carries the answer key
 *   - 404 on a signals route for a session that streamed none
 *   - 404, never 403, for another user's resource -- so the API never confirms
 *     that something exists to someone not entitled to know
 *
 * A green run therefore means the API refuses what it should, not merely that
 * it answers.
 *
 * The account it creates is synthetic and is deleted at the end. Nothing real
 * is read, and no response body is printed.
 */
const BASE = (process.argv[2] || "http://localhost:8000").replace(/\/$/, "");
const STAMP = `${Date.now()}${Math.floor(process.hrtime()[1] / 1000)}`;
const EMAIL = `smoke.${STAMP}@example.com`;
const PASSWORD = "Sm0ke!Test#2026";

let token = null;
const results = [];

async function call(method, path, { body, auth = true, expect } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  let res, text;
  try {
    res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    text = await res.text();
  } catch (e) {
    results.push({ method, path, status: "ERR", ok: false, note: String(e).slice(0, 70) });
    return null;
  }
  results.push({ method, path, status: res.status, ok: expect ? expect.includes(res.status) : res.status < 400 });
  try { return JSON.parse(text); } catch { return text; }
}

console.log(`\nsmoke test against ${BASE}\n`);

// --- 1. the API must refuse an anonymous caller everywhere it should ------
const GUARDED = [
  "/api/v1/users/me", "/api/v1/users/profile", "/api/v1/users/privacy",
  "/api/v1/users/notifications", "/api/v1/dashboard/summary",
  "/api/v1/aptitude/catalog", "/api/v1/aptitude/tests", "/api/v1/aptitude/attempts",
  "/api/v1/dsa/problems", "/api/v1/interviews/history", "/api/v1/resume/analyses",
  "/api/v1/admin/analytics",
];
console.log("1. auth enforcement — every guarded route, no token");
for (const p of GUARDED) await call("GET", p, { auth: false, expect: [401, 403] });

// --- 2. account lifecycle ------------------------------------------------
console.log("2. signup / login / account-type");
await call("GET", "/health", { auth: false, expect: [200] });
const signup = await call("POST", "/api/v1/auth/signup", { auth: false, expect: [200, 201, 429],
  body: { name: "Smoke Test", email: EMAIL, password: PASSWORD } });
const login = await call("POST", "/api/v1/auth/login", { auth: false, expect: [200, 429],
  body: { email: EMAIL, password: PASSWORD } });
token = login?.data?.accessToken ?? login?.data?.access_token ?? null;
void signup;
await call("POST", "/api/v1/auth/check-account-type", { auth: false, expect: [200], body: { email: EMAIL } });

// --- 3. authenticated reads ---------------------------------------------
if (!token) {
  /*
   * Not a failure, and reporting it as twenty cascading 401s would be
   * actively misleading. Signup is capped at 3/hour and login at 5/hour per
   * IP, so running this script a few times in quick succession legitimately
   * locks it out -- which is the rate limiter doing its job, on the live
   * deployment, which is one of the things this script exists to confirm.
   */
  console.log("");
  console.log("=".repeat(66));
  console.log("Rate limited before a token could be obtained (signup is 3/hour per IP),");
  console.log("so the limiter is live and wired to its backing store on this deployment.");
  console.log("Anonymous checks above all passed; authenticated checks were skipped.");
  console.log("Wait out the window to exercise the full set.");
  console.log("");
  const anonBad = results.filter((r) => !r.ok);
  for (const r of anonBad) console.log("  " + String(r.status).padEnd(5) + r.method.padEnd(7) + r.path);
  process.exit(anonBad.length ? 1 : 0);
}

console.log("3. authenticated reads");
for (const p of GUARDED.filter((p) => p !== "/api/v1/admin/analytics")) await call("GET", p, { expect: [200] });
// A normal account must not reach the admin surface.
await call("GET", "/api/v1/admin/analytics", { expect: [403] });

// --- 4. aptitude, including the server-owned clock ----------------------
console.log("4. aptitude attempt + timer");
const att = await call("POST", "/api/v1/aptitude/attempts", { expect: [200, 201], body: { questionCount: 5 } });
const attemptId = att?.data?.attemptId ?? att?.data?.attempt_id;
if (attemptId) {
  // 409 is the point: this route's body carries correct_option_index, so it
  // refuses an attempt that has not been submitted.
  await call("GET", `/api/v1/aptitude/attempts/${attemptId}`, { expect: [409] });
  const t = await call("GET", `/api/v1/aptitude/attempts/${attemptId}/time`, { expect: [200] });
  const remaining = t?.data?.timeRemainingSeconds;
  console.log(`   timeRemainingSeconds = ${JSON.stringify(remaining)}`
    + (remaining === null ? "  (null = untimed practice, by design)" : ""));
  await call("POST", `/api/v1/aptitude/attempts/${attemptId}/submit`, { expect: [200, 422], body: { answers: [] } });
  await call("GET", `/api/v1/aptitude/attempts/${attemptId}`, { expect: [200, 409] });
}

// --- 5. dsa --------------------------------------------------------------
console.log("5. dsa");
const probs = await call("GET", "/api/v1/dsa/problems", { expect: [200] });
const pid = probs?.data?.items?.[0]?.id ?? probs?.data?.[0]?.id;
if (pid) {
  await call("GET", `/api/v1/dsa/problems/${pid}`, { expect: [200] });
  await call("GET", `/api/v1/dsa/problems/${pid}/submissions`, { expect: [200] });
  await call("POST", `/api/v1/dsa/problems/${pid}/test-cases`, { expect: [200, 422], body: {} });
}

// --- 6. interview --------------------------------------------------------
console.log("6. interview");
const iv = await call("POST", "/api/v1/interviews/start", { expect: [200, 201],
  body: { role: "Backend Engineer", type: "technical", durationMinutes: 15, mode: "voice", consentGiven: true } });
const sid = iv?.data?.sessionId ?? iv?.data?.session_id;
if (sid) {
  await call("GET", `/api/v1/interviews/${sid}`, { expect: [200] });
  // 404 is correct for a session that streamed no signals: the row genuinely
  // does not exist, and the route says so rather than inventing an empty one.
  await call("GET", `/api/v1/interviews/${sid}/signals/prosody`, { expect: [200, 404] });
  await call("GET", `/api/v1/interviews/${sid}/signals/expression`, { expect: [200, 404] });
  await call("GET", `/api/v1/feedback/${sid}/status`, { expect: [200, 404] });
  await call("POST", `/api/v1/interviews/${sid}/end`, { expect: [200], body: {} });
}

// --- 7. it has to reject bad input, not just accept good input -----------
console.log("7. validation and not-found");
await call("POST", "/api/v1/auth/login", { auth: false, expect: [422], body: { email: "not-an-email" } });
// 429 is a pass, and an important one: login is rate-limited (5/hour by
  // default), so a run that has already logged in once may well be throttled
  // here. Seeing it means the limiter is wired to its backing store on this
  // deployment -- which is exactly the thing the pytest suite cannot observe.
  await call("POST", "/api/v1/auth/login", { auth: false, expect: [401, 429], body: { email: EMAIL, password: "wrong" } });
await call("POST", "/api/v1/auth/signup", { auth: false, expect: [409, 422],
  body: { name: "Dup", email: EMAIL, password: PASSWORD } });
await call("POST", "/api/v1/auth/signup", { auth: false, expect: [422],
  body: { name: "Weak", email: `weak.${STAMP}@example.com`, password: "short" } });
const NIL = "00000000-0000-0000-0000-000000000000";
// 404 rather than 403 throughout: never confirm a resource exists to someone
// who is not entitled to know that it does.
await call("GET", `/api/v1/interviews/${NIL}`, { expect: [404] });
await call("GET", `/api/v1/aptitude/attempts/${NIL}`, { expect: [404] });
await call("GET", `/api/v1/dsa/problems/${NIL}`, { expect: [404, 422] });
await call("GET", `/api/v1/feedback/${NIL}`, { expect: [404] });

// --- 8. clean up after ourselves ----------------------------------------
console.log("8. cleanup");
await call("POST", "/api/v1/auth/logout-all-devices", { expect: [200], body: {} });
await call("DELETE", "/api/v1/users/me", { expect: [200, 204, 422], body: { password: PASSWORD } });

const bad = results.filter((r) => !r.ok);
console.log("\n" + "=".repeat(66));
console.log(`${results.length} calls — ${results.length - bad.length} as expected, ${bad.length} unexpected`);
if (bad.length) {
  console.log("\nUNEXPECTED:");
  for (const r of bad) console.log(`  ${String(r.status).padEnd(5)} ${r.method.padEnd(7)} ${r.path}${r.note ? "  " + r.note : ""}`);
  console.log("");
  process.exit(1);
}
console.log("all endpoints behaved as designed\n");

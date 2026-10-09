"""Auth/scoring constants kept in one place so policy is easy to audit/tune."""

# Progressive account lockout (Section 12.1): after this many consecutive
# failed logins, lockout kicks in — cooldown escalates on each further
# failure using the ladder below (index = failures beyond the threshold,
# clamped to the last entry).
FAILED_LOGIN_LOCKOUT_THRESHOLD = 5
LOCKOUT_LADDER_MINUTES = [1, 5, 30, 60]

# Readiness Index weights (Section 10.2) now live in the `scoring_weights`
# config table, as the spec requires ("store in a config table, not hardcoded
# ... so they can be tuned later without a redeploy"). Phase 4 built that
# table; read them with `app.services.feedback.scoring.load_index_weights(db)`.
# The Section 10.2 published defaults are the fallback in that module, used
# only when no active row exists.

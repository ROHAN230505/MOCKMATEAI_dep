"""
Who has an account, and when they last signed in.

    python scripts/inspect_users.py              # emails masked
    python scripts/inspect_users.py --full       # emails in full
    python scripts/inspect_users.py --sessions   # per-user activity too

## Why "when did they log in" is not a column

`users` has no `last_login_at`, and adding one would be a second source of
truth for something already recorded: a login mints a refresh token, so
`refresh_tokens.created_at` IS the login history, with one row per session and
`revoked` telling you which were logged out. That is also why "logged in" below
means "started a session", not "is online now" -- the API is stateless and
nothing tracks presence.

## Why emails are masked by default

A terminal gets copied into chats, screenshots and tickets. Masking is the
right default for a tool whose whole output is personal data; `--full` is one
flag away when you actually need to identify someone.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.user import RefreshToken, User  # noqa: E402


def mask(email: str) -> str:
    """j***@example.com -- enough to recognise an account you already know."""
    local, _, domain = email.partition("@")
    head = local[0] if local else "?"
    return f"{head}{'*' * max(2, len(local) - 1)}@{domain}"


def when(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "never"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="show full email addresses")
    parser.add_argument("--sessions", action="store_true", help="include per-user activity counts")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        users = db.scalars(select(User).order_by(User.created_at.desc()).limit(args.limit)).all()
        if not users:
            print("\nNo accounts yet.\n")
            return

        # One query for all login stats rather than one per user.
        logins = dict(
            db.execute(
                select(RefreshToken.user_id, func.count()).group_by(RefreshToken.user_id)
            ).all()
        )
        last_login = dict(
            db.execute(
                select(RefreshToken.user_id, func.max(RefreshToken.created_at)).group_by(
                    RefreshToken.user_id
                )
            ).all()
        )
        live = dict(
            db.execute(
                select(RefreshToken.user_id, func.count())
                .where(RefreshToken.revoked.is_(False))
                .group_by(RefreshToken.user_id)
            ).all()
        )

        print(f"\n{len(users)} account(s), newest first" + ("" if args.full else "  (emails masked — use --full)"))
        print("=" * 104)
        print(f"{'EMAIL':34} {'NAME':18} {'VIA':9} {'SIGNED UP':17} {'LAST LOGIN':17} {'LOGINS':>6} {'LIVE':>5}")
        print("-" * 104)
        for user in users:
            shown = user.email if args.full else mask(user.email)
            print(
                f"{shown[:33]:34} {user.name[:17]:18} {user.auth_provider.value:9} "
                f"{when(user.created_at):17} {when(last_login.get(user.id)):17} "
                f"{logins.get(user.id, 0):>6} {live.get(user.id, 0):>5}"
            )

        locked = [u for u in users if u.locked_until]
        if locked:
            print(f"\n{len(locked)} locked out by failed logins:")
            for user in locked:
                shown = user.email if args.full else mask(user.email)
                print(f"   {shown}  until {when(user.locked_until)}  ({user.failed_login_attempts} attempts)")

        if args.sessions:
            from app.models.aptitude import AptitudeAttempt
            from app.models.dsa import DSASubmission
            from app.models.interview import InterviewSession

            print("\nactivity")
            print("-" * 104)
            print(f"{'EMAIL':34} {'INTERVIEWS':>11} {'APTITUDE':>9} {'DSA SUBS':>9}")
            for user in users:
                shown = user.email if args.full else mask(user.email)
                counts = [
                    db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id))
                    for model in (InterviewSession, AptitudeAttempt, DSASubmission)
                ]
                if any(counts):
                    print(f"{shown[:33]:34} {counts[0]:>11} {counts[1]:>9} {counts[2]:>9}")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    main()

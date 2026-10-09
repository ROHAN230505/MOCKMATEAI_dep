"""
Guessable-password rejection (`app/core/password_blocklist.py`).

These exist because the policy they replaced was composition-only -- length,
one digit, one symbol -- and accepted every password in this file's first list.
Each of those is at the top of published breach corpora, so the old policy was
demanding a ritual rather than buying any safety.
"""
import pytest

from app.core.password_blocklist import common_password_reason
from app.core.security import validate_password_policy

# All of these passed the old composition-only policy.
NOTORIOUS = [
    "Password1!", "password1!", "PASSWORD1!", "Passw0rd!", "P@ssw0rd", "p@ssw0rd1",
    "Qwerty12!", "qwerty123", "Qwertyuiop1!", "Asdfgh12!", "Zxcvbn12!",
    "Welcome1!", "welcome123", "Letmein1!", "letmein123",
    "Iloveyou1!", "iloveyou123", "Monkey123!", "Dragon2024!", "Sunshine1!",
    "Admin123!", "admin1234!", "Master123!", "Shadow123!", "Football1!",
    "Princess1!", "Michael123!", "Jesus123!", "Trustno1!", "Whatever1!",
]

# Long, unusual, and not about the user. These must NOT be rejected: a check
# that fires on these trains people to fight the form instead of picking well.
STRONG = [
    "Tr0ub4dor&3xyz", "correct-horse-battery-9!", "Vx7#qLm2!pZ",
    "my-tabby-ate-3-socks!", "gl4cier-Mosaic-77#", "Quiet$Harbour19",
]


@pytest.mark.parametrize("password", NOTORIOUS)
def test_notorious_passwords_are_rejected(password):
    assert common_password_reason(password) is not None, password


@pytest.mark.parametrize("password", STRONG)
def test_strong_passwords_are_accepted(password):
    assert common_password_reason(password) is None, password


@pytest.mark.parametrize("password", ["12345678", "1234567890!", "abcdefgh", "hgfedcba!"])
def test_sequences_are_rejected(password):
    assert "sequence" in (common_password_reason(password) or "")


@pytest.mark.parametrize("password", ["abababab", "aaaaaaaa", "123123123!", "xyxyxyxy"])
def test_repeated_patterns_are_rejected(password):
    assert common_password_reason(password) is not None


def test_leetspeak_does_not_rescue_a_common_word():
    """`P@ssw0rd` is the canonical example of complexity theatre."""
    assert common_password_reason("P@ssw0rd") is not None
    assert common_password_reason("l3tm31n!") is not None


def test_appended_padding_does_not_rescue_a_common_word():
    """The digits people add to satisfy the composition rule are not entropy."""
    for suffix in ("1", "1!", "123", "2024", "007", "!!"):
        assert common_password_reason("welcome" + suffix) is not None, suffix


def test_the_service_name_is_rejected():
    assert common_password_reason("MockMate2026!") is not None
    assert common_password_reason("interview-time-9!") is not None


def test_a_password_containing_the_users_own_identity_is_rejected():
    reason = common_password_reason(
        "Priyasharma-9-xk!", email="priya.sharma@example.com", name="Priya Sharma"
    )
    assert reason is not None and "name or email" in reason


def test_short_identity_fragments_do_not_cause_false_positives():
    """
    Banning three-letter fragments would reject any password containing them.
    `ali` from ali@x.com must not make `Quality-Harbour-9!` unusable.
    """
    assert common_password_reason("Quality-Harbour-9!", email="ali@example.com", name="Ali") is None


def test_identity_is_only_checked_when_supplied():
    """Signup has it; some callers do not. Absence must not crash or over-reject."""
    assert common_password_reason("Quiet$Harbour19") is None


# --- integration with the policy the API actually calls -------------------
def test_the_policy_now_rejects_what_it_used_to_accept():
    assert validate_password_policy("Password1!") != []
    assert validate_password_policy("Qwerty12!") != []


def test_the_policy_still_accepts_a_good_password():
    assert validate_password_policy("my-tabby-ate-3-socks!") == []


def test_composition_failures_are_reported_alone():
    """
    Telling someone their 5-character password is *also* a common one is two
    complaints about the same keystroke.
    """
    errors = validate_password_policy("pass")
    assert errors
    assert not any("commonly used" in e for e in errors)

"""
Rejecting passwords that are common, predictable, or about the user.

## Why this exists

The policy before this checked length, one digit, one symbol -- and accepted
`Password1!`, `Qwerty12!`, `letmein1!`, `iloveyou1!` and `P@ssw0rd`. Those are
not edge cases; they are the top of every breach corpus ever published. A rule
set that demands a symbol and then waves through `P@ssw0rd` has taught the user
a ritual rather than bought them any safety.

## Why a base-word list rather than a password list

A literal list of common passwords needs millions of entries to be useful,
because `password`, `Password1`, `P@ssw0rd!` and `password2024` are four
separate strings. Normalising first -- folding leetspeak, stripping the
padding people add to satisfy exactly the kind of rule above -- collapses all
four onto one base word, so a few hundred bases outperform a list thousands of
times larger.

That is also the honest framing of the threat: an attacker's dictionary is
generated the same way, from bases plus mutations. Matching on the base is
matching on what they actually try.

## What this is not

It is not a breach check. `is_breached_password` in `security.py` does that
against HaveIBeenPwned, needs network, and is off by default. This one is
offline, deterministic, and always on -- so a deployment with no outbound
access still refuses the obvious.
"""
from __future__ import annotations

import re

# Leetspeak folded before matching, so `P@ssw0rd` and `pa55word` both reduce to
# `password`. Deliberately one-way and lossy: the point is to collapse
# mutations onto a base, not to reconstruct what the user typed.
_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s", "!": "i", "|": "i", "+": "t",
})

# The bases attackers actually try first, drawn from the recurring top of
# published breach corpora. Stored as bases, not as finished passwords: the
# normaliser strips the digits and punctuation people append to satisfy a
# complexity rule, so `welcome` here already covers `Welcome1!`, `welcome123`
# and `W3lc0me!`.
COMMON_BASE_WORDS: frozenset[str] = frozenset({
    # the perennials
    "password", "passwd", "pass", "secret", "letmein", "welcome", "admin",
    "administrator", "root", "login", "guest", "user", "test", "demo", "temp",
    "changeme", "default", "master", "manager", "supervisor", "access",
    # keyboard walks
    "qwerty", "qwertyui", "qwertyuiop", "asdf", "asdfgh", "asdfghjkl", "zxcv",
    "zxcvbn", "zxcvbnm", "qazwsx", "qweasd", "wasd", "poiuy", "lkjh", "mnbv",
    "qwertz", "azerty", "1q2w3e", "1qaz2wsx", "q1w2e3", "abc", "abcd", "abcdef",
    # affection and profanity, both extremely common
    "iloveyou", "loveyou", "love", "lovely", "sunshine", "princess", "angel",
    "baby", "babygirl", "sweetie", "darling", "kisses", "forever",
    "fuckyou", "fuckoff", "fuck", "shit", "bitch", "asshole", "bullshit",
    # names, teams, culture
    "michael", "jennifer", "jessica", "ashley", "michelle", "daniel", "david",
    "thomas", "robert", "joshua", "andrew", "matthew", "hunter", "george",
    "charlie", "jordan", "taylor", "nicole", "amanda", "samantha", "anthony",
    "krishna", "sairam", "ganesh", "rahul", "priya", "amit", "sachin", "kumar",
    "arsenal", "liverpool", "chelsea", "barcelona", "madrid", "manutd",
    "united", "rangers", "celtic", "cricket", "football", "soccer", "baseball",
    "basketball", "hockey", "sports", "batman", "superman", "spiderman",
    "pokemon", "naruto", "starwars", "matrix", "ninja", "dragon", "phoenix",
    "shadow", "hunter2", "gandalf", "aragorn", "thor", "joker",
    # animals, objects, the rest of the long tail
    "monkey", "dragon", "tiger", "lion", "eagle", "falcon", "panther", "cobra",
    "snake", "bear", "wolf", "fish", "bird", "dolphin", "butterfly",
    "computer", "internet", "google", "facebook", "yahoo", "hotmail", "gmail",
    "amazon", "netflix", "spotify", "android", "iphone", "samsung", "windows",
    "linux", "server", "database", "oracle", "mysql", "postgres", "redis",
    "money", "freedom", "whatever", "trustno", "nothing", "anything",
    "summer", "winter", "spring", "autumn", "january", "february", "december",
    "monday", "friday", "sunday", "today", "tomorrow",
    "flower", "orange", "purple", "yellow", "silver", "golden", "diamond",
    "guitar", "music", "player", "gamer", "gaming", "minecraft", "fortnite",
    "chocolate", "cookie", "coffee", "pepper", "cheese", "banana", "apple",
    "hello", "hellothere", "whatsup", "goodluck", "happy", "smile", "peace",
    "jesus", "allah", "heaven", "church", "faith", "grace", "amen",
    "school", "college", "student", "teacher", "office", "work", "company",
    "mobile", "phone", "india", "america", "london", "paris", "tokyo", "canada",
    "killer", "hacker", "legend", "boss", "king", "queen", "prince", "champion",
    "asshole", "sexy", "hotstuff", "blowjob", "pussy", "porn", "xxx",
})

# Words about this product. A password containing the name of the thing it
# protects is guessed first by anyone attacking this specific system.
PRODUCT_WORDS: frozenset[str] = frozenset({
    "mockmate", "mockmateai", "mockinterview", "interview", "interviewer",
})

_MIN_CONTEXT_FRAGMENT = 4


def _fold(password: str) -> str:
    """Lowercase and fold leetspeak, so mutations collapse onto their base."""
    return password.lower().translate(_LEET)


def _strip_padding(folded: str) -> str:
    """
    Strip the decoration bolted on to satisfy a complexity rule.

    `Password1!` becomes `password`, `2024welcome!!` becomes `welcome`. This is
    the step that makes a few hundred bases behave like a list of millions --
    and it mirrors how an attacker's dictionary is generated in the first place.
    """
    return re.sub(r"^[^a-z]+|[^a-z]+$", "", folded)


# Runs long enough to contain any wrap-around a password can walk through.
# `1234567890` is the single most common password on earth and a naive
# adjacent-difference test misses it, because 9 -> 0 is a step of -9 rather
# than +1. Substring matching against a doubled run has no such seam.
_DIGIT_RUN = "01234567890123456789"
_ALPHA_RUN = "abcdefghijklmnopqrstuvwxyz"


def _is_sequential(candidate: str) -> bool:
    """`12345678`, `1234567890`, `abcdefgh`, and their descending forms."""
    if len(candidate) < 4:
        return False
    for run in (_DIGIT_RUN, _ALPHA_RUN):
        if candidate in run or candidate in run[::-1]:
            return True
    return False


def _is_repetitive(folded: str) -> bool:
    """
    `aaaaaaaa`, `abababab`, `123123123` -- a short cycle repeated to length.

    Checked up to a THIRD of the length, not a quarter. At a quarter the loop
    never even tested a 3-character cycle in a 9-character password, so
    `123123123` -- which is about as guessable as a password gets -- sailed
    through. Three repeats is a pattern; two is a coincidence worth allowing.
    """
    if len(folded) < 4:
        return False
    for size in range(1, len(folded) // 3 + 1):
        if folded == folded[:size] * (len(folded) // size) + folded[: len(folded) % size]:
            return True
    return False


def _context_fragments(*values: str | None) -> set[str]:
    """
    Words from the user's own identity that must not appear in their password.

    An email local part is split on separators, so `priya.sharma@x.com` yields
    `priya` and `sharma` as well as `priya.sharma`. Fragments shorter than four
    characters are dropped: banning `ali` would reject any password containing
    "quality", which is a rule that annoys without protecting.
    """
    out: set[str] = set()
    for value in values:
        if not value:
            continue
        head = value.split("@", 1)[0]
        for part in re.split(r"[^a-z0-9]+", head.lower()):
            if len(part) >= _MIN_CONTEXT_FRAGMENT:
                out.add(part)
        collapsed = re.sub(r"[^a-z0-9]+", "", head.lower())
        if len(collapsed) >= _MIN_CONTEXT_FRAGMENT:
            out.add(collapsed)
    return out


def _candidates(password: str) -> set[str]:
    """
    Every plausible base this password could be a mutation of.

    A SET, not a chain, because the two normalisations interfere: folding
    leetspeak rewrites `1` and `!` into letters, which destroys exactly the
    signal `_strip_padding` needs to recognise them as decoration. Fold first
    and `Password1!` becomes `passwordii`; strip first and it becomes
    `password`. Neither order is right on its own, so try both and also the
    unfolded form, and match if any of them lands on a known base.
    """
    lower = password.lower()
    folded = _fold(password)
    return {
        lower,
        folded,
        _strip_padding(lower),
        _strip_padding(folded),
        _fold(_strip_padding(lower)),
    } - {""}


def _trimmed(password: str) -> str:
    """Lowercased with leading/trailing punctuation removed, digits intact.

    Sequences and repeats have to be judged before leetspeak folding --
    `12345678` folds to `ieeasbtb`, which is not a sequence any more."""
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", password.lower())


def common_password_reason(
    password: str,
    *,
    email: str | None = None,
    name: str | None = None,
) -> str | None:
    """
    Why this password is guessable, or None if it survives every check.

    Returns prose rather than an error code because it is shown to the user,
    and the wording is the point: "must not be a common password" teaches
    nothing, where naming the actual pattern tells them what to avoid.
    """
    trimmed = _trimmed(password)
    if _is_sequential(trimmed):
        return "Password must not be a sequence like 12345678 or abcdefgh."
    if trimmed and _is_repetitive(trimmed):
        return "Password must not be a short pattern repeated, like abababab."

    candidates = _candidates(password)
    if candidates & COMMON_BASE_WORDS:
        return (
            "Password is one of the most commonly used passwords, even with numbers or "
            "symbols added. Attackers try these first."
        )
    if candidates & PRODUCT_WORDS or any(w in _fold(password) for w in PRODUCT_WORDS):
        return "Password must not contain the name of this service."

    folded = _fold(password)
    lower = password.lower()
    for fragment in _context_fragments(email, name):
        if fragment in folded or fragment in lower:
            return "Password must not contain your name or email address."
    return None

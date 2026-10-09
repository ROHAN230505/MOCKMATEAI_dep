"""
Every HTTP route carries a rate limit.

A coverage assertion rather than a behaviour one, and deliberately so: an
unlimited route is not a bug anyone notices. It passes review, passes its own
tests, serves traffic correctly, and is simply free to hammer. Fifteen of
fifty-five routes were in that state -- including the OAuth ticket exchange,
which takes an opaque credential and returns a token pair, and account
deletion, which is irreversible.

So this walks the router source and fails on anything undecorated. It is
source inspection rather than runtime introspection because slowapi records
limits on the endpoint function, and a decorator applied in the wrong order
registers nothing while still looking right at the call site.
"""
import pathlib
import re

ROUTERS = pathlib.Path(__file__).resolve().parent.parent / "app" / "routers"
_ROUTE = re.compile(r"\s*@router\.(get|post|put|patch|delete)\(")
_DEF = re.compile(r"\s*(async )?def (\w+)")


def _routes_without_limits() -> list[str]:
    offenders = []
    for path in sorted(ROUTERS.glob("*.py")):
        lines = path.read_text(encoding="utf-8").split("\n")
        for index, line in enumerate(lines):
            if not _ROUTE.match(line):
                continue
            # The decorator stack sits between @router and the def.
            window = []
            for cursor in range(index + 1, min(index + 8, len(lines))):
                window.append(lines[cursor])
                if _DEF.match(lines[cursor]):
                    break
            if any("limiter.limit" in entry for entry in window):
                continue
            name = next((_DEF.match(e).group(2) for e in window if _DEF.match(e)), "?")
            offenders.append(f"{path.name}::{name}")
    return offenders


def test_every_http_route_has_a_rate_limit():
    offenders = _routes_without_limits()
    assert offenders == [], (
        "These routes have no @limiter.limit decorator, so they can be called "
        "without bound:\n  " + "\n  ".join(offenders)
    )


def test_the_check_actually_finds_routes():
    """A coverage test that silently matches nothing would pass forever."""
    total = sum(
        len([line for line in path.read_text(encoding="utf-8").split("\n") if _ROUTE.match(line)])
        for path in ROUTERS.glob("*.py")
    )
    assert total > 40, f"only found {total} routes — the pattern has stopped matching"

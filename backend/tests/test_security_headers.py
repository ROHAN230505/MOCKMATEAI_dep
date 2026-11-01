

# --- the documentation pages need their own assets --------------------------
def test_the_docs_page_may_load_its_own_bundle(client):
    """
    `default-src 'none'` is right for a JSON API and wrong for the one route
    that serves HTML: it blocks the script that renders the page, and the
    result is a blank white screen with nothing in the UI to say why. The HTML
    arrives, the bundle never does.
    """
    csp = client.get("/docs").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp
    assert "script-src" in csp


def test_the_docs_exception_does_not_leak_to_the_api(client):
    """The relaxation is for two pages, not for the API it documents."""
    csp = client.get("/health").headers["content-security-policy"]
    assert csp == "default-src 'none'; frame-ancestors 'none'"
    assert "jsdelivr" not in csp


def test_the_docs_csp_is_still_restrictive(client):
    """Narrowed to what the page uses, not opened up."""
    csp = client.get("/docs").headers["content-security-policy"]
    assert csp.startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in csp
    # No blanket wildcard anywhere in the policy.
    assert " *" not in csp

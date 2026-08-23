# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Class ratchets over the probe bridge sources (round 10, R10-1/R10-2).

These are source-level guards because their subject is a *class*, not an
instance: no single test case covers "CORS came back", "a probe half
stopped carrying the token", or "the installer regressed to a bypassable
URL regex" - each is a whole-file shape that must hold across every
future edit of js/. The behavioral half of this net lives in the probe
selftest, which drives the real bridge through these same failure paths;
this file catches what that test cannot see (the browser installer has no
DOM in CI, and a header deleted from a file no test exercises).

Doctrine 3.6 says selector counting measures nothing - so where presence
of a string is all we can assert (the installer's URL parsing), the test
SAYS that is what it is: a construction guard, weaker than behavior,
better than nothing.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_DIR = REPO_ROOT / "js"
TOKEN_HEADER = "x-sutradhar-probe-token"


def _probe_sources() -> dict[Path, str]:
    """Every shipped JS/TS source of the probe layer, by path."""
    return {
        p: p.read_text(encoding="utf-8")
        for p in sorted(JS_DIR.rglob("*"))
        if p.is_file() and p.suffix in (".mjs", ".ts")
    }


def test_no_cors_permission_is_shipped_anywhere_in_the_probe_layer():
    """R10-1 class guard: `access-control-allow-origin` served only hostile
    webpages - every legitimate client is curl, MCP, or the page itself.
    If any file ever reintroduces it, this fails and the diff must argue
    why a browser needs permission from a loopback dev tool."""
    offenders = [
        path
        for path, src in _probe_sources().items()
        if re.search(r"access-control-allow-(origin|headers)", src, re.IGNORECASE)
        # the selftest may NAME the header in order to assert its absence
        and "selftest" not in path.name
    ]
    assert not offenders, (
        "CORS permission headers reappeared in the probe layer "
        f"{[str(p.relative_to(REPO_ROOT)) for p in offenders]} - they exist "
        "to serve cross-origin browsers, which are exactly the attacker "
        "this layer refuses. See docs/design/probe-auth.md before changing."
    )


@pytest.mark.parametrize(
    "relpath",
    ["js/probe/server.mjs", "js/probe/core.mjs", "js/probe/mcp.mjs"],
)
def test_every_half_of_the_transport_carries_the_token(relpath):
    """The bridge checks the token, the page sends it, the MCP adapter
    sends it. A half that drops it either breaks the loop (core) or goes
    dark at the gate (mcp) - but only if someone notices. This notices."""
    src = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert TOKEN_HEADER in src, (
        f"{relpath} no longer references '{TOKEN_HEADER}' - the transport "
        "has lost its credential on one side. See docs/design/probe-auth.md."
    )


def test_installer_parses_bridge_urls_and_requires_a_token():
    """R10-2 construction guard: the old regex accepted
    `http://127.0.0.1@evil.example`. The installer must decide with the
    URL parser's hostname and must demand the token. Asserted here by
    construction because CI has no DOM to drive installProbe with - a
    string-presence check per doctrine 3.6 measures little, and is still
    the difference between a regression being caught and shipping."""
    src = (REPO_ROOT / "js/probe/browser.mjs").read_text(encoding="utf-8")
    assert "new URL(" in src, "installer must parse bridge URLs with new URL(), not regex"
    assert ".hostname" in src, "installer must check parsed.hostname, not the front of the string"
    assert TOKEN_HEADER in src or "token" in src, (
        "installer no longer demands the bridge token"
    )


def test_probe_token_meets_declared_entropy():
    """Budget "probe-auth" from docs/design/probe-auth.md: the generated
    token carries >= 128 bits. Enforced against the generator call in the
    bridge source, so raising the note's number forces this to argue with
    the code and shrinking the code fails the note."""
    budget_id = "probe-auth"
    declared_bits = 128  # the n: in probe-auth's frontmatter
    src = (REPO_ROOT / "js/probe/server.mjs").read_text(encoding="utf-8")
    match = re.search(r"crypto\.randomBytes\((\d+)\)\.toString\(", src)
    assert match, "bridge no longer generates its token via crypto.randomBytes - update this guard deliberately if the generator changed"
    bits = int(match.group(1)) * 8
    assert bits >= declared_bits, (
        f"budget {budget_id}: generated token entropy fell to {bits} bits, below "
        f"the {declared_bits} bits declared in docs/design/probe-auth.md"
    )


def test_selftest_exercises_the_refusal_paths_it_claims():
    """Wiring guard (the test_detectors_and_wiring pattern): the selftest's
    docstring claims the refusal paths are tested as first-class cases.
    If the cases are deleted from the selftest, this fails - a suite that
    no longer contains them must not keep the claim."""
    src = (REPO_ROOT / "js/probe/selftest.mjs").read_text(encoding="utf-8")
    for marker in (
        '"/probe/poll"',        # impersonation refusal
        "malformed result",     # payload-shape refusal
        "access-control-allow-origin",  # permission-withheld assertion
        "413",                  # oversized-body refusal
    ):
        assert marker in src, f"probe selftest lost its {marker!r} case"

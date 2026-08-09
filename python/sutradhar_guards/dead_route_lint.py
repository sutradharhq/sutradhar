#!/usr/bin/env python3
"""Guard: an e2e test must not assert against a route the API does not serve.

The incident (2026-08-05). A suite carried 44 assertions of the shape

    expect(res.status).to.not.eq(500)

across 10 specs. That assertion passes on 404 — so a test pointed at a route
that does not exist is GREEN FOREVER. Checked against the app's own route
table, 28 references resolved to nothing: an entire retired API prefix, three
analytics endpoints, an audit surface that had moved, and two that had merely
changed shape. Those tests had been reporting success for months while
asserting nothing whatsoever about the product.

The harness in place at the time could not have caught it. Its frontend rules
covered reachability and EFFECT for the UI; nothing covered the API layer,
and nothing anywhere asked the sharper question: **can this assertion fail at
all?**

Two independent detectors, because they catch different halves:

  `find_unfailable_assertions` — the assertion is too weak to fail. Asserting
  "not 500" or "not 404" tolerates every other wrong answer; assert the
  contract you expect instead.

  `find_dead_routes` — the URL under test is absent from the API's route
  table. Even a strong assertion is worthless if it is aimed at nothing.

Both are stack-agnostic: give `find_dead_routes` the set of routes your API
actually serves (OpenAPI `paths`, a Rails routes dump, an Express router
walk) and it does the rest.

Usage:
    from sutradhar_guards.dead_route_lint import (
        find_dead_routes, find_unfailable_assertions,
    )
    from sutradhar_guards.ratchet import Ratchet

    def test_specs_hit_real_routes():
        routes = set(requests.get(f"{API}/openapi.json").json()["paths"])
        Ratchet("tests/baselines/dead_routes.json").assert_only_shrinks(
            find_dead_routes("e2e/", routes)
        )
"""
from __future__ import annotations

import re
from pathlib import Path

# `url: "/foo/bar"` / `url: `${BASE}/foo/bar`` / `fetch("/foo")`.
# `(?<!\w)` is load-bearing: without it this also matches `drill_url:`, which
# in a SPA carries a FRONTEND route, not an API path — a false positive that
# sends you "fixing" a perfectly good route. Narrow the detector, never
# allowlist the finding.
_URL_RE = re.compile(
    r"""(?<!\w)(?:url|path)\s*:\s*[`'"]\s*(?:\$\{[^}]*\})?([^`'"]*)"""
)
_FETCH_RE = re.compile(r"""(?:fetch|request|get|post)\(\s*[`'"](?:\$\{[^}]*\})?(/[^`'"]*)""")

# "not this one specific failure" — passes on every OTHER wrong answer.
_UNFAILABLE_RE = re.compile(
    r"""\.to\.not\.eq\(\s*(?:500|404|403|401)\s*\)"""
    r"""|!==\s*(?:500|404)"""
    r"""|\.not\.to\.equal\(\s*(?:500|404)\s*\)"""
)


def _normalise(raw: str) -> str | None:
    """Spec URL -> comparable API path, or None when not checkable."""
    raw = raw.strip()
    if not raw.startswith("/"):
        return None                       # relative / fully interpolated base
    raw = raw.split("?", 1)[0]
    if "${" in raw or "{" in raw and "}" in raw:
        raw = re.sub(r"\$?\{[^}]*\}", "{param}", raw)
    return raw.rstrip("/") or "/"


def route_matches(path: str, routes: set[str]) -> bool:
    """True when `path` is served, treating {param} as a wildcard.

    Tolerates a trailing-slash difference: most frameworks redirect `/x` to
    `/x/`, so flagging it is a false positive and a guard that cries wolf
    gets muted.
    """
    if path in routes or path + "/" in routes or path.rstrip("/") in routes:
        return True
    p_parts = path.split("/")
    for r in routes:
        r_parts = r.rstrip("/").split("/")
        if len(r_parts) != len(p_parts):
            continue
        if all(
            rp == pp or rp.startswith("{") or rp.startswith(":") or pp == "{param}"
            for rp, pp in zip(r_parts, p_parts)
        ):
            return True
    return False


def _spec_files(root: str | Path, patterns: tuple[str, ...]) -> list[Path]:
    root = Path(root)
    out: list[Path] = []
    for pat in patterns:
        out.extend(f for f in root.rglob(pat) if "node_modules" not in str(f))
    return sorted(set(out))


def find_dead_routes(
    spec_root: str | Path,
    routes: set[str],
    patterns: tuple[str, ...] = ("*.cy.ts", "*.cy.js", "*.spec.ts", "*.e2e.ts"),
) -> list[str]:
    """`spec:path` for every URL under test that the API does not serve."""
    dead: set[str] = set()
    for spec in _spec_files(spec_root, patterns):
        text = spec.read_text(errors="replace")
        for regex in (_URL_RE, _FETCH_RE):
            for raw in regex.findall(text):
                norm = _normalise(raw)
                if norm and not route_matches(norm, routes):
                    dead.add(f"{spec.name}:{norm}")
    return sorted(dead)


def find_unfailable_assertions(
    spec_root: str | Path,
    patterns: tuple[str, ...] = ("*.cy.ts", "*.cy.js", "*.spec.ts", "*.e2e.ts"),
) -> list[str]:
    """`spec:line` for every assertion that only excludes ONE bad outcome."""
    out: list[str] = []
    for spec in _spec_files(spec_root, patterns):
        for i, line in enumerate(spec.read_text(errors="replace").splitlines(), 1):
            if _UNFAILABLE_RE.search(line):
                out.append(f"{spec.name}:{i}")
    return out


# ── selfcheck ───────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    routes = {"/real", "/users/{id}", "/nested/"}
    ok = (
        route_matches("/real", routes)
        and route_matches("/users/{param}", routes)
        and route_matches("/nested", routes)          # trailing-slash tolerance
        and not route_matches("/ghost", routes)
        and bool(_UNFAILABLE_RE.search("expect(res.status).to.not.eq(500);"))
        and not _UNFAILABLE_RE.search("expect(res.status).to.eq(200);")
        and _normalise("/instances?x=1") == "/instances"
        and _normalise("relative/path") is None
    )
    if not ok:
        print("[dead-route] SELFCHECK FAILED — detector is not discriminating")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if selfcheck() else 1)

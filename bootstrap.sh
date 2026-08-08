#!/usr/bin/env bash
# Sutradhar bootstrap - copy the harness into a target repo.
#
# Usage:  bash bootstrap.sh /path/to/your/repo
#
# Copies (never overwrites - existing files are skipped with a notice):
#   python guards  -> <repo>/scripts/ + <repo>/tests/sutradhar/
#   ui guards      -> <repo>/cypress/support/uiGuards.ts (+ example spec)
#   ci template    -> <repo>/.github/workflows/guards.yml
#   agent rules    -> <repo>/AGENTS.sutradhar.md (append/link it yourself)
#   skills         -> <repo>/.claude/skills/ if .claude exists, else <repo>/agent-skills/
#
# Everything copied is yours to edit; there is no upstream to track.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:?usage: bash bootstrap.sh /path/to/your/repo}"
TARGET="$(cd "$TARGET" && pwd)"

copied=0
skipped=0

copy() { # copy <src> <dest>
  local src="$1" dest="$2"
  if [ -e "$dest" ]; then
    echo "  skip (exists): ${dest#"$TARGET"/}"
    skipped=$((skipped + 1))
  else
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "  copied:        ${dest#"$TARGET"/}"
    copied=$((copied + 1))
  fi
}

echo "Sutradhar -> $TARGET"

echo "python guards:"
copy "$HERE/python/sutradhar_guards/swallow_lint.py"       "$TARGET/scripts/swallow_lint.py"
copy "$HERE/python/sutradhar_guards/interpolation_lint.py" "$TARGET/scripts/interpolation_lint.py"
copy "$HERE/python/sutradhar_guards/verify_guard.py"       "$TARGET/scripts/verify_guard.py"
copy "$HERE/python/sutradhar_guards/ratchet.py"            "$TARGET/tests/sutradhar/ratchet.py"
copy "$HERE/python/sutradhar_guards/envgate.py"            "$TARGET/tests/sutradhar/envgate.py"

echo "ui guards:"
copy "$HERE/js/cypress/uiGuards.ts"             "$TARGET/cypress/support/uiGuards.ts"
copy "$HERE/js/cypress/routeSweep.example.cy.ts" "$TARGET/cypress/e2e/routeSweep.example.cy.ts"

copy "$HERE/python/sutradhar_guards/claim_check.py"        "$TARGET/tests/sutradhar/claim_check.py"
copy "$HERE/python/sutradhar_guards/golden.py"             "$TARGET/tests/sutradhar/golden.py"
copy "$HERE/python/sutradhar_guards/detectors.py"          "$TARGET/tests/sutradhar/detectors.py"

echo "runtime probe:"
copy "$HERE/js/probe/core.mjs"    "$TARGET/probe/core.mjs"
copy "$HERE/js/probe/browser.mjs" "$TARGET/probe/browser.mjs"
copy "$HERE/js/probe/server.mjs"  "$TARGET/probe/server.mjs"
copy "$HERE/js/probe/mcp.mjs"     "$TARGET/probe/mcp.mjs"
copy "$HERE/js/probe/README.md"   "$TARGET/probe/README.md"

echo "ci:"
copy "$HERE/ci/guards.yml" "$TARGET/.github/workflows/guards.yml"

echo "agent rules + skills:"
copy "$HERE/agent/AGENTS.md" "$TARGET/AGENTS.sutradhar.md"
if [ -d "$TARGET/.claude" ]; then
  SKILLS_DIR="$TARGET/.claude/skills"
else
  SKILLS_DIR="$TARGET/agent-skills"
fi
copy "$HERE/agent/skills/robustness-loop.md" "$SKILLS_DIR/robustness-loop/SKILL.md"
copy "$HERE/agent/skills/ops-drill.md"       "$SKILLS_DIR/ops-drill/SKILL.md"

echo "docs (reference copies):"
copy "$HERE/DOCTRINE.md" "$TARGET/docs/sutradhar-doctrine.md"

echo
echo "done: $copied copied, $skipped skipped (existing files untouched)"
echo
echo "next steps:"
echo "  1. record today's floor:   python scripts/swallow_lint.py <src>/ --update-baseline --baseline scripts/swallow_baseline.json"
echo "  2. run the injection lint: python scripts/interpolation_lint.py <src>/ --keywords sql"
echo "  2b. prove your next fix's guard is real:"
echo "      python scripts/verify_guard.py --guard-cmd \"pytest tests/test_the_fix.py\""
echo "  3. configure uiGuards in cypress/support/e2e.ts and adapt the route sweep"
echo "  4. append AGENTS.sutradhar.md to your CLAUDE.md / AGENTS.md"
echo "  5. adjust .github/workflows/guards.yml paths to your layout"
echo
echo "adoption guide: $HERE/docs/adoption.md"

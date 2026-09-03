#!/usr/bin/env bash
# Sutradhar bootstrap - copy the harness into a target repo.
#
# Usage:  bash bootstrap.sh /path/to/your/repo [--layers a,b,c]
#
# Layers (default: all):
#   python   guards      -> <repo>/scripts/ + <repo>/tests/sutradhar/
#   frontend ui guards   -> <repo>/cypress/support/uiGuards.ts (+ example spec)
#   probe    runtime probe -> <repo>/probe/
#   ci       workflow    -> <repo>/.github/workflows/guards.yml
#   agent    rules+skills -> <repo>/AGENTS.sutradhar.md, skills dir, agent-packs/
#   docs     doctrine + design-note template + obs floor
#
#   bash bootstrap.sh . --layers python,ci,agent,docs   # a backend service
#
# A backend-only repo that takes every layer gets a cypress suite it will never
# run and a CI job that fails on a missing JS lockfile - which reads as the
# harness being broken. Take what you will use.
#
# Everything copied is yours to edit; there is no upstream to track.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:?usage: bash bootstrap.sh /path/to/your/repo [--layers python,frontend,probe,ci,agent,docs]}"
TARGET="$(cd "$TARGET" && pwd)"
shift

ALL_LAYERS="python frontend probe ci agent docs"
LAYERS="$ALL_LAYERS"
while [ $# -gt 0 ]; do
  case "$1" in
    --layers)
      LAYERS="$(echo "${2:?--layers needs a comma-separated list}" | tr ',' ' ')"
      shift 2
      ;;
    --layers=*)
      LAYERS="$(echo "${1#*=}" | tr ',' ' ')"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: bash bootstrap.sh /path/to/your/repo [--layers $(echo "$ALL_LAYERS" | tr ' ' ',')]" >&2
      exit 2
      ;;
  esac
done

# An unknown layer is refused, never ignored: silently skipping a typo'd
# `--layers pyhton` would copy nothing and report success (doctrine 2.4).
for layer in $LAYERS; do
  case " $ALL_LAYERS " in
    *" $layer "*) ;;
    *) echo "unknown layer: $layer (known: $(echo "$ALL_LAYERS" | tr ' ' ','))" >&2; exit 2 ;;
  esac
done

want() { case " $LAYERS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

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

if want python; then
echo "python guards:"
copy "$HERE/python/sutradhar_guards/swallow_lint.py"       "$TARGET/scripts/swallow_lint.py"
copy "$HERE/python/sutradhar_guards/interpolation_lint.py" "$TARGET/scripts/interpolation_lint.py"
copy "$HERE/python/sutradhar_guards/verify_guard.py"       "$TARGET/scripts/verify_guard.py"
copy "$HERE/python/sutradhar_guards/budget.py"             "$TARGET/scripts/budget.py"
copy "$HERE/python/sutradhar_guards/rounds.py"             "$TARGET/scripts/rounds.py"
copy "$HERE/python/sutradhar_guards/obsgate.py"            "$TARGET/scripts/obsgate.py"
copy "$HERE/python/sutradhar_guards/ratchet.py"            "$TARGET/tests/sutradhar/ratchet.py"
copy "$HERE/python/sutradhar_guards/envgate.py"            "$TARGET/tests/sutradhar/envgate.py"
copy "$HERE/python/sutradhar_guards/claim_check.py"        "$TARGET/tests/sutradhar/claim_check.py"
copy "$HERE/python/sutradhar_guards/golden.py"             "$TARGET/tests/sutradhar/golden.py"
copy "$HERE/python/sutradhar_guards/detectors.py"          "$TARGET/tests/sutradhar/detectors.py"
# A place for the loop's records, so `rounds --check` in CI has a directory to
# read rather than failing on a missing path on the adopter's first push.
mkdir -p "$TARGET/docs/rounds"
fi

if want frontend; then
echo "ui guards:"
copy "$HERE/js/cypress/uiGuards.ts"             "$TARGET/cypress/support/uiGuards.ts"
copy "$HERE/js/cypress/uiGuards.selftest.mjs"  "$TARGET/cypress/support/uiGuards.selftest.mjs"
copy "$HERE/js/cypress/routeSweep.example.cy.ts" "$TARGET/cypress/e2e/routeSweep.example.cy.ts"
fi

if want probe; then
echo "runtime probe:"
copy "$HERE/js/probe/core.mjs"    "$TARGET/probe/core.mjs"
copy "$HERE/js/probe/browser.mjs" "$TARGET/probe/browser.mjs"
copy "$HERE/js/probe/server.mjs"  "$TARGET/probe/server.mjs"
copy "$HERE/js/probe/mcp.mjs"     "$TARGET/probe/mcp.mjs"
copy "$HERE/js/probe/README.md"   "$TARGET/probe/README.md"
fi

if want ci; then
echo "ci:"
copy "$HERE/ci/guards.yml" "$TARGET/.github/workflows/guards.yml"
fi

if want agent; then
echo "agent rules + skills:"
copy "$HERE/agent/AGENTS.md" "$TARGET/AGENTS.sutradhar.md"
if [ -d "$TARGET/.claude" ]; then
  SKILLS_DIR="$TARGET/.claude/skills"
else
  SKILLS_DIR="$TARGET/agent-skills"
fi
copy "$HERE/agent/skills/robustness-loop.md" "$SKILLS_DIR/robustness-loop/SKILL.md"
copy "$HERE/agent/skills/ops-drill.md"       "$SKILLS_DIR/ops-drill/SKILL.md"
# The condensed forms, for the rules files that will not take 15KB.
copy "$HERE/agent/packs/README.md"           "$TARGET/agent-packs/README.md"
copy "$HERE/agent/packs/CLAUDE-snippet.md"   "$TARGET/agent-packs/CLAUDE-snippet.md"
copy "$HERE/agent/packs/cursor.rules.md"     "$TARGET/agent-packs/cursor.rules.md"
fi

if want docs; then
echo "docs (reference copies):"
copy "$HERE/DOCTRINE.md" "$TARGET/docs/sutradhar-doctrine.md"

# Apache-2.0 section 4(d): a redistribution must carry the NOTICE. The
# copied files keep their own headers; this puts the notice where a reader
# of YOUR repo will find it. Using it privately requires nothing - only
# passing it on carries the requirement.
echo "attribution:"
copy "$HERE/NOTICE" "$TARGET/NOTICE.sutradhar"
copy "$HERE/docs/templates/design-note.md" "$TARGET/docs/design/TEMPLATE.md"
copy "$HERE/docs/templates/backflow.md"    "$TARGET/docs/backflow.md"
copy "$HERE/docs/templates/obs_floor.json" "$TARGET/obs_floor.json"
fi

echo
echo "layers: $LAYERS"
echo "done: $copied copied, $skipped skipped (existing files untouched)"
echo
echo "next steps:"
echo "  1. record today's floor:   python scripts/swallow_lint.py <src>/ --update-baseline --baseline scripts/swallow_baseline.json"
echo "  2. run the injection lint: python scripts/interpolation_lint.py <src>/ --keywords sql"
echo "  2c. after each robustness round: python scripts/rounds.py docs/rounds/ --floors ."
echo "  2e. decide what your other repos have learned:"
echo "      python scripts/rounds.py docs/rounds/ --backflow docs/backflow.md"
echo "  2a. gate your declared budgets: python scripts/budget.py docs/design/ --tests tests/"
echo "  2d. edit obs_floor.json to your metric names, then: python scripts/obsgate.py --metrics <url> --floor obs_floor.json"
echo "  2b. prove your next fix's guard is real:"
echo "      python scripts/verify_guard.py --guard-cmd \"pytest tests/test_the_fix.py\""
echo "  3. configure uiGuards in cypress/support/e2e.ts and adapt the route sweep"
echo "     prove the effect digest still sees form state:"
echo "       node cypress/support/uiGuards.selftest.mjs"
echo "  4. append AGENTS.sutradhar.md to your CLAUDE.md / AGENTS.md"
echo "     (or the one-page form: cat agent-packs/CLAUDE-snippet.md >> CLAUDE.md;"
echo "      Cursor: cp agent-packs/cursor.rules.md .cursorrules)"
echo "  5. adjust .github/workflows/guards.yml paths to your layout"
echo
echo "adoption guide: $HERE/docs/adoption.md"

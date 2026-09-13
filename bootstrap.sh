#!/usr/bin/env bash
# Sutradhar bootstrap - copy the harness into a target repo.
#
# Usage:  bash bootstrap.sh /path/to/your/repo [--layers a,b,c]
#         bash bootstrap.sh --check /path/to/your/repo   # which release, and what is behind
#         bash bootstrap.sh --track /path/to/your/repo   # start the record in an older tree
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
# Everything copied is yours to edit. What is recorded is where it came from:
# bootstrap writes `.sutradhar-bootstrap` into the target - the release, and a
# sha256 of every file it placed - so `--check`, run from a newer checkout, can
# tell a copy that has fallen behind from one you changed on purpose. Two
# adopting trees ran copies missing a detection this repository had added weeks
# earlier, and nothing could tell them (R21-6). The check is offline: the
# checkout you run it from is the comparison. The copied files themselves carry
# no version header, because a copy must stay byte-identical to its source.
#
# `--check` exits 0 when nothing is behind, 1 when a file is stale, 2 when it
# could not check. A file you modified or deleted is reported and never fails:
# both are yours to do. A tree with no record is reported as not tracked, with
# the command that starts tracking, and exits 0.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USAGE="usage: bash bootstrap.sh [--check | --track] /path/to/your/repo [--layers python,frontend,probe,ci,agent,docs]"

# A dotfile at the target's root, beside `.sutradhar-owners`, in plain
# tab-separated text so nothing is needed to read it but a shell.
RECORD=".sutradhar-bootstrap"

MODE=copy
case "${1:-}" in
  --check|--track) MODE="${1#--}"; shift ;;
esac

TARGET="${1:?$USAGE}"
if [ ! -d "$TARGET" ]; then
  echo "not a directory: $TARGET" >&2
  echo "$USAGE" >&2
  exit 2
fi
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
    --check|--track)
      MODE="${1#--}"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "$USAGE" >&2
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
say() { if [ "$MODE" = copy ]; then echo "$@"; fi; }

# The release this checkout is, read as text rather than by importing the
# package: bootstrap has to run where Python does not.
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$HERE/python/sutradhar_guards/__init__.py" 2>/dev/null || true)"
VERSION="${VERSION:-unknown}"
COMMIT="$(git -C "$HERE" rev-parse --short=12 HEAD 2>/dev/null || true)"
COMMIT="${COMMIT:--}"

sha256_of() { # sha256_of <file> -> hex digest on stdout; returns 1 with no hasher
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d' ' -f1
  else
    return 1
  fi
}
HASHER=yes
sha256_of "$HERE/bootstrap.sh" >/dev/null 2>&1 || HASHER=no

TAB="$(printf '\t')"

# ── --check: offline, against this checkout ─────────────────────────────────

check_record() {
  local rec="$TARGET/$RECORD"
  echo "Sutradhar --check: $TARGET"
  echo "against the checkout at $HERE (release $VERSION, commit $COMMIT)"
  if [ ! -f "$rec" ]; then
    echo
    echo "not tracked: this tree has no $RECORD, so which release its copies came"
    echo "from cannot be told. It was bootstrapped before the record existed, or"
    echo "copied by hand. That is not a failure, and nothing here is red."
    echo "To start tracking, from this checkout:"
    echo
    echo "    bash $HERE/bootstrap.sh --track $TARGET"
    echo
    exit 0
  fi
  if [ "$HASHER" = no ]; then
    echo "could not check: neither sha256sum nor shasum is on PATH, so no file can be" >&2
    echo "compared. This is not a pass (2.9)." >&2
    exit 2
  fi

  local n_rows=0 n_current=0 n_stale=0 n_modified=0 n_missing=0 lineno=0
  local releases="" diffs="" kind hash rel dest src now state note
  while IFS="$TAB" read -r kind hash rel dest src; do
    lineno=$((lineno + 1))
    case "$kind" in
      ''|'#'*|written-by) continue ;;
      file) ;;
      *)
        # Refused, never skipped: a row the reader cannot parse would
        # otherwise vanish, and the file it names would never be checked.
        echo "could not check: $rec line $lineno is not a record row ($kind)." >&2
        exit 2
        ;;
    esac
    if [ -z "$src" ] || ! printf '%s' "$hash" | grep -Eq '^[0-9a-f]{64}$'; then
      echo "could not check: $rec line $lineno is malformed; a row is" >&2
      echo "file<TAB>sha256<TAB>release<TAB>path-here<TAB>path-in-sutradhar." >&2
      exit 2
    fi
    n_rows=$((n_rows + 1))
    releases="$releases$rel$TAB"
    note=""
    if [ ! -e "$TARGET/$dest" ]; then
      state="missing"
      n_missing=$((n_missing + 1))
    else
      now="$(sha256_of "$TARGET/$dest")"
      if [ -f "$HERE/$src" ] && [ "$now" = "$(sha256_of "$HERE/$src")" ]; then
        state="current"
        n_current=$((n_current + 1))
      elif [ "$now" != "$hash" ]; then
        state="modified locally"
        n_modified=$((n_modified + 1))
        note="changed since it was recorded; diff it against $src to see whether it is also behind"
      else
        state="stale"
        n_stale=$((n_stale + 1))
        if [ -f "$HERE/$src" ]; then
          note="unchanged since it was recorded, and this checkout's $src has moved on"
          diffs="$diffs    diff $TARGET/$dest $HERE/$src
"
        else
          note="unchanged since it was recorded, and this checkout no longer ships $src"
        fi
      fi
    fi
    printf '  %-16s %s (taken from release %s)\n' "$state" "$dest" "$rel"
    if [ -n "$note" ]; then
      printf '  %-16s   %s\n' "" "$note"
    fi
  done < "$rec"

  if [ "$n_rows" -eq 0 ]; then
    echo "could not check: $rec lists no file. An empty record and a tree with" >&2
    echo "nothing behind look identical from here, so this is a refusal, not a pass." >&2
    exit 2
  fi
  local taken
  taken="$(printf '%s' "$releases" | tr '\t' '\n' | sort -u | paste -sd, - | sed 's/,/, /g')"
  echo
  echo "this tree took release(s) $taken; this checkout is release $VERSION"
  echo "$n_current current, $n_stale stale, $n_modified modified locally, $n_missing missing"
  if [ "$n_stale" -gt 0 ]; then
    echo
    echo "A stale file is one nobody here changed and this checkout has moved past - a"
    echo "detection added since, or a fix. Read what changed:"
    printf '%s' "$diffs"
    echo "then take the new copy by moving yours aside and re-running bootstrap.sh,"
    echo "which records it."
    exit 1
  fi
  exit 0
}

if [ "$MODE" = check ]; then
  check_record
fi

# ── the record: what was placed, from which release ─────────────────────────

if [ "$MODE" = track ] && [ "$HASHER" = no ]; then
  echo "could not track: neither sha256sum nor shasum is on PATH, so nothing can be" >&2
  echo "recorded. Nothing was written." >&2
  exit 2
fi

ENTRIES="$(mktemp "${TMPDIR:-/tmp}/sutradhar-record.XXXXXX")"
trap 'rm -f "$ENTRIES"' EXIT

record_entry() { # record_entry <release> <src relative to HERE> <dest relative to TARGET>
  local hash
  hash="$(sha256_of "$TARGET/$3")" || return 0
  printf 'file\t%s\t%s\t%s\t%s\n' "$hash" "$1" "$3" "$2" >> "$ENTRIES"
}

recorded_already() { # recorded_already <dest relative to TARGET>
  [ -f "$TARGET/$RECORD" ] || return 1
  awk -F'\t' -v d="$1" '$1 == "file" && $4 == d { found = 1 } END { exit !found }' "$TARGET/$RECORD"
}

write_record() {
  local rec="$TARGET/$RECORD" tmp="$TARGET/$RECORD.tmp.$$"
  {
    echo "# Sutradhar bootstrap record: which files bootstrap.sh placed in this tree,"
    echo "# the release each came from, and its sha256 when recorded. Read, from any"
    echo "# Sutradhar checkout, by:  bash bootstrap.sh --check <this repository>"
    echo "# Edit the copied files freely. Do not edit this file: a hash changed here"
    echo "# hides a local modification from that check. Commit it."
    printf 'written-by\t%s\t%s\n' "$VERSION" "$COMMIT"
    if [ -f "$rec" ]; then
      # Keep every earlier row this run did not replace. FILENAME rather than
      # NR == FNR: with no fresh rows the first file is empty, and the usual
      # idiom would then read the old record as the fresh one.
      awk -F'\t' -v fresh_file="$ENTRIES" '
        FILENAME == fresh_file { if ($1 == "file") fresh[$4] = 1; next }
        $1 == "file" && !($4 in fresh) { print }
      ' "$ENTRIES" "$rec"
    fi
    cat "$ENTRIES"
  } > "$tmp"
  mv "$tmp" "$rec"
}

copied=0
skipped=0
unrecorded=0
tracked_same=0
tracked_differ=0

copy() { # copy <src> <dest>
  local src="$1" dest="$2"
  local src_rel="${src#"$HERE"/}" dest_rel="${dest#"$TARGET"/}"
  if [ "$MODE" = track ]; then
    if [ -e "$dest" ] && ! recorded_already "$dest_rel"; then
      if [ "$(sha256_of "$dest")" = "$(sha256_of "$src")" ]; then
        record_entry "$VERSION" "$src_rel" "$dest_rel"
        tracked_same=$((tracked_same + 1))
      else
        record_entry "unknown" "$src_rel" "$dest_rel"
        tracked_differ=$((tracked_differ + 1))
      fi
    fi
    return 0
  fi
  if [ -e "$dest" ]; then
    echo "  skip (exists): $dest_rel"
    skipped=$((skipped + 1))
    if ! recorded_already "$dest_rel"; then
      # Byte-identical to this checkout is provably this release's copy.
      # Anything else could be an older release or a local edit, and a
      # record that guessed would make --check lie about it.
      if [ "$HASHER" = yes ] && [ "$(sha256_of "$dest")" = "$(sha256_of "$src")" ]; then
        record_entry "$VERSION" "$src_rel" "$dest_rel"
      else
        unrecorded=$((unrecorded + 1))
      fi
    fi
  else
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "  copied:        $dest_rel"
    copied=$((copied + 1))
    if [ "$HASHER" = yes ]; then
      record_entry "$VERSION" "$src_rel" "$dest_rel"
    fi
  fi
}

say "Sutradhar -> $TARGET"

if want python; then
say "python guards:"
copy "$HERE/python/sutradhar_guards/swallow_lint.py"       "$TARGET/scripts/swallow_lint.py"
copy "$HERE/python/sutradhar_guards/interpolation_lint.py" "$TARGET/scripts/interpolation_lint.py"
copy "$HERE/python/sutradhar_guards/conflated_degrade_lint.py" "$TARGET/scripts/conflated_degrade_lint.py"
copy "$HERE/python/sutradhar_guards/ci_step_lint.py"       "$TARGET/scripts/ci_step_lint.py"
copy "$HERE/python/sutradhar_guards/ownership_lint.py"     "$TARGET/scripts/ownership_lint.py"
# framework_only.py and framework_shape.py are deliberately NOT copied.
# Both gate a promise only THIS repository makes - no dependencies, and no
# business domain in the shipped surface. In your tree they would scan
# directories holding nothing but the files you just copied, so they can
# only ever pass: a guard that cannot fail where you run it is decoration
# (doctrine 2.2), and telling you to run one teaches a green that means
# nothing. You are building a product; speaking your own domain is the
# point.
copy "$HERE/python/sutradhar_guards/verify_guard.py"       "$TARGET/scripts/verify_guard.py"
copy "$HERE/python/sutradhar_guards/budget.py"             "$TARGET/scripts/budget.py"
copy "$HERE/python/sutradhar_guards/rounds.py"             "$TARGET/scripts/rounds.py"
copy "$HERE/python/sutradhar_guards/obsgate.py"            "$TARGET/scripts/obsgate.py"
copy "$HERE/python/sutradhar_guards/ratchet.py"            "$TARGET/tests/sutradhar/ratchet.py"
copy "$HERE/python/sutradhar_guards/envgate.py"            "$TARGET/tests/sutradhar/envgate.py"
copy "$HERE/python/sutradhar_guards/claim_check.py"        "$TARGET/tests/sutradhar/claim_check.py"
copy "$HERE/python/sutradhar_guards/golden.py"             "$TARGET/tests/sutradhar/golden.py"
copy "$HERE/python/sutradhar_guards/detectors.py"          "$TARGET/tests/sutradhar/detectors.py"
copy "$HERE/python/sutradhar_guards/dead_route_lint.py"    "$TARGET/tests/sutradhar/dead_route_lint.py"
# A place for the loop's records, so `rounds --check` in CI has a directory to
# read rather than failing on a missing path on the adopter's first push.
if [ "$MODE" = copy ]; then
  mkdir -p "$TARGET/docs/rounds"
fi
fi

if want frontend; then
say "ui guards:"
copy "$HERE/js/cypress/uiGuards.ts"             "$TARGET/cypress/support/uiGuards.ts"
copy "$HERE/js/cypress/uiGuards.selftest.mjs"  "$TARGET/cypress/support/uiGuards.selftest.mjs"
copy "$HERE/js/cypress/routeSweep.example.cy.ts" "$TARGET/cypress/e2e/routeSweep.example.cy.ts"
fi

if want probe; then
say "runtime probe:"
copy "$HERE/js/probe/core.mjs"    "$TARGET/probe/core.mjs"
copy "$HERE/js/probe/browser.mjs" "$TARGET/probe/browser.mjs"
copy "$HERE/js/probe/server.mjs"  "$TARGET/probe/server.mjs"
copy "$HERE/js/probe/mcp.mjs"     "$TARGET/probe/mcp.mjs"
copy "$HERE/js/probe/README.md"   "$TARGET/probe/README.md"
fi

if want ci; then
say "ci:"
copy "$HERE/ci/guards.yml" "$TARGET/.github/workflows/guards.yml"
fi

if want agent; then
say "agent rules + skills:"
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
say "docs (reference copies):"
copy "$HERE/DOCTRINE.md" "$TARGET/docs/sutradhar-doctrine.md"

# Apache-2.0 section 4(d): a redistribution must carry the NOTICE. The
# copied files keep their own headers; this puts the notice where a reader
# of YOUR repo will find it. Using it privately requires nothing - only
# passing it on carries the requirement.
say "attribution:"
copy "$HERE/NOTICE" "$TARGET/NOTICE.sutradhar"
copy "$HERE/docs/templates/design-note.md" "$TARGET/docs/design/TEMPLATE.md"
copy "$HERE/docs/templates/backflow.md"    "$TARGET/docs/backflow.md"
copy "$HERE/docs/templates/obs_floor.json" "$TARGET/obs_floor.json"
fi

if [ "$MODE" = track ]; then
  echo "Sutradhar --track: $TARGET"
  if [ ! -s "$ENTRIES" ]; then
    if [ -f "$TARGET/$RECORD" ]; then
      echo "nothing new to record: every Sutradhar file present is already in $RECORD."
      exit 0
    fi
    echo "could not track: no file is where bootstrap.sh puts one (layers: $LAYERS)," >&2
    echo "so there is nothing to record. Nothing was written." >&2
    exit 2
  fi
  write_record
  echo "recorded $tracked_same file(s) byte-identical to this checkout, as release $VERSION"
  if [ "$tracked_differ" -gt 0 ]; then
    echo "recorded $tracked_differ file(s) that differ from this checkout, as found and"
    echo "with release unknown. Whether each is an older release or your own edit cannot"
    echo "be told from here; from today, --check reports it stale while it stays as it is."
  fi
  echo "check it from any checkout: bash $HERE/bootstrap.sh --check $TARGET"
  exit 0
fi

echo
echo "layers: $LAYERS"
echo "done: $copied copied, $skipped skipped (existing files untouched)"
if [ "$HASHER" = no ]; then
  echo "record: NOT written - neither sha256sum nor shasum is on PATH. The copy is"
  echo "complete; only --check will be unable to say whether these files fall behind."
elif [ -s "$ENTRIES" ]; then
  write_record
  echo "record: $RECORD lists where each placed file came from (release $VERSION); commit it"
fi
if [ "$unrecorded" -gt 0 ]; then
  echo "record: $unrecorded existing file(s) differ from this checkout and are not in the"
  echo "        record, so where they came from cannot be told. To record them as found:"
  echo "        bash $HERE/bootstrap.sh --track $TARGET"
fi
echo
echo "next steps:"
echo "  1. record today's floor:   python scripts/swallow_lint.py <src>/ --update-baseline --baseline scripts/swallow_baseline.json"
echo "  2. run the injection lint: python scripts/interpolation_lint.py <src>/ --keywords sql"
echo "  2g. record the conflated-degrade floor - a failed read that reads as an empty one:"
echo "      python scripts/conflated_degrade_lint.py <src>/ --update-baseline"
echo "      (1, 2 and 2g read Python. Pointed at a path with no .py file they exit 2"
echo "       and say nothing was scanned, rather than print OK over nothing. No"
echo "       Python in this tree: skip them, and delete their three CI steps.)"
echo "  2h. make sure every CI step can reach the script it names:"
echo "      python scripts/ci_step_lint.py ."
echo "  2j. if more than one agent works this tree, declare who owns what in"
echo "      .sutradhar-owners and refuse a stage that reaches into someone else's:"
echo "      python scripts/ownership_lint.py --owner <your-agent-name>"
echo "  2c. after each robustness round: python scripts/rounds.py docs/rounds/ --floors ."
echo "  2e. decide what your other repos have learned:"
echo "      python scripts/rounds.py docs/rounds/ --backflow docs/backflow.md"
echo "  2f. make every design note name what paid for it:"
echo "      python scripts/rounds.py docs/rounds/ --designs docs/design/"
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
echo "  6. when you pull a newer Sutradhar, ask it which of these copies fell behind:"
echo "      bash <that checkout>/bootstrap.sh --check $TARGET"
echo
echo "adoption guide: $HERE/docs/adoption.md"

#!/usr/bin/env bash
# Sutradhar examples - watch seven real defects surface from a codebase
# whose own test suite is green.
#
#   bash examples/run-the-guards.sh
#
# Needs: python3 and pytest. Nothing else, no install, no network.
#
# This script EXPECTS the guards to go red - that is the demonstration. It
# exits 0 when every planted defect was caught and nonzero when one was
# missed, because a demo that has quietly stopped demonstrating is the
# decoration this whole framework is about.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
APP="$HERE/broken-app"
G="$ROOT/python/sutradhar_guards"
PY="${PYTHON:-python3}"

pass=0
missed=0
step=0

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
dim()  { printf "\033[2m%s\033[0m\n" "$1"; }

caught() {  # caught <what the guard found>
  step=$((step + 1)); pass=$((pass + 1))
  printf "  \033[32m%d. CAUGHT\033[0m  %s\n" "$step" "$1"
}
missed_it() {
  step=$((step + 1)); missed=$((missed + 1))
  printf "  \033[31m%d. MISSED\033[0m  %s\n" "$step" "$1"
}

echo
bold "── First, the app's own test suite ──────────────────────────────────"
echo
( cd "$APP" && "$PY" -m pytest tests/ -q 2>&1 | tail -3 )
echo
dim "  Green. Five passed, one skipped. Every defect below is present in"
dim "  that codebase right now, and not one of those tests can see any of"
dim "  them. This is the state most codebases are in."
echo
bold "── Now the guards ───────────────────────────────────────────────────"
echo

# 1. silent swallow (doctrine 2.7)
out=$("$PY" "$G/swallow_lint.py" "$APP/app" --baseline "$APP/.no-baseline.json" 2>&1); rc=$?
if [ $rc -ne 0 ] && echo "$out" | grep -q "readings.py"; then
  caught "silent exception swallow - readings.py turns an outage into {}, which
             downstream code reads as 'this meter reported nothing'"
else
  missed_it "swallow_lint did not flag readings.py"
fi

# 2. unbounded ORDER BY (doctrine 2.6)
out=$(cd "$ROOT" && "$PY" -c "
import sys; sys.path.insert(0, 'python')
from sutradhar_guards.detectors import find_order_by_without_limit
hits = find_order_by_without_limit(open('$APP/app/readings.py').read())
print('readings.py:' + ', '.join(str(h) for h in hits))
sys.exit(0 if hits else 1)"); rc=$?
if [ $rc -eq 0 ]; then
  caught "unbounded ORDER BY at $out - the history query sorts a table that
             grows with every reading, with no LIMIT"
else
  missed_it "the ORDER BY detector found nothing"
fi

# 3. query interpolation (doctrine 2.8)
out=$("$PY" "$G/interpolation_lint.py" "$APP/app" --keywords sql 2>&1); rc=$?
if [ $rc -ne 0 ]; then
  caught "SQL built by interpolation - safe today because the caller passes an
             int, a hole the moment anyone parameterises it"
else
  missed_it "interpolation_lint found nothing"
fi

# 4. fabricated numbers in generated text (doctrine 4.1)
out=$(cd "$ROOT" && "$PY" -c "
import sys; sys.path.insert(0, 'python'); sys.path.insert(0, '$APP')
from sutradhar_guards.claim_check import ground_claims
from app.report import summarise
text = summarise(usage_kwh=980, change_pct=12)
bad = ground_claims(text, [{'value': 980, 'unit': 'kWh'}, {'value': 12, 'unit': '%'}])
print(', '.join(c['raw'] for c in bad))
sys.exit(0 if bad else 1)"); rc=$?
if [ $rc -eq 0 ]; then
  caught "invented numbers in model output - the summary says $out, and the
             witnessed values were 980 kWh and 12%"
else
  missed_it "claim_check grounded everything"
fi

# 5. a skip gate nothing sets (the ~86-test incident)
out=$(cd "$ROOT" && "$PY" -c "
import sys; sys.path.insert(0, 'python')
from sutradhar_guards.envgate import audit_skip_gates, EnvGate
missing = audit_skip_gates(
    [EnvGate(marker='billing_integration', env_var='BILLING_TESTS', reason='billing stack')],
    search_globs=['.github/workflows/*.yml', 'Makefile'], root='$APP')
print(', '.join(missing))
sys.exit(0 if missing else 1)"); rc=$?
if [ $rc -eq 0 ]; then
  caught "a skip gate nothing sets - $out is set by no workflow, so the billing
             arithmetic test has never executed anywhere, and the suite counts it"
else
  missed_it "the skip-gate audit passed"
fi

# 6. a budget declared and never enforced (doctrine 1.1)
out=$("$PY" "$G/budget.py" "$APP/docs/design" --tests "$APP/tests" 2>&1); rc=$?
if [ $rc -eq 1 ] && echo "$out" | grep -q "reading-sweep"; then
  caught "a budget nobody enforces - the design note promises 200,000 meters
             inside 800ms, and no test holds it to that"
else
  missed_it "the budget gate did not flag reading-sweep"
fi

# 7. a guard that cannot fail (doctrine 2.2) - needs real commits, so build
#    a throwaway repo: parent without the discount, then the 'fix'.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/app" "$TMP/tests"
cp "$APP/app/__init__.py" "$TMP/app/" 2>/dev/null || : > "$TMP/app/__init__.py"
: > "$TMP/tests/__init__.py"
cat > "$TMP/app/billing.py" <<'PYEOF'
def total(units, rate):
    return units * rate
PYEOF
git -C "$TMP" init -q
git -C "$TMP" -c user.email=e@x.invalid -c user.name=n add -A >/dev/null
git -C "$TMP" -c user.email=e@x.invalid -c user.name=n -c commit.gpgsign=false \
    commit -q -m "billing, before the bulk discount"
cp "$APP/app/billing.py" "$TMP/app/billing.py"
cp "$APP/tests/test_billing.py" "$TMP/tests/test_billing.py"
git -C "$TMP" -c user.email=e@x.invalid -c user.name=n add -A >/dev/null
git -C "$TMP" -c user.email=e@x.invalid -c user.name=n -c commit.gpgsign=false \
    commit -q -m "fix: apply the bulk discount, with a test"

out=$("$PY" "$G/verify_guard.py" --repo "$TMP" --commit HEAD \
      --guard-cmd "$PY -m pytest tests/test_billing.py -q" 2>&1); rc=$?
if [ $rc -eq 1 ] && echo "$out" | grep -q "DECORATION"; then
  caught "a test that cannot fail - test_billing.py re-implements the discount
             locally and never calls total(). Revert the fix and it stays green"
else
  missed_it "verify_guard did not report DECORATION (exit $rc)"
fi

echo
bold "── Result ───────────────────────────────────────────────────────────"
echo
if [ $missed -eq 0 ]; then
  printf "  \033[32m%d of %d planted defects caught.\033[0m\n" "$pass" "$step"
  echo
  dim "  None of them were found by reading the code, and none of them were"
  dim "  found by the app's own passing test suite. That gap is the whole"
  dim "  argument: a green suite is evidence of nothing until something has"
  dim "  shown it can go red."
  echo
  dim "  Walkthrough of each defect, and the fix: examples/README.md"
  echo
  exit 0
fi
printf "  \033[31m%d of %d caught - %d MISSED.\033[0m\n" "$pass" "$step" "$missed"
echo
dim "  A missed defect means a guard has stopped working or the example"
dim "  drifted. Either way this demo is currently lying, which is worse"
dim "  than not shipping it. See examples/README.md."
echo
exit 1

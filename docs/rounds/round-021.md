# Round 21 - 2026-09-13

Lenses: the backflow register, instruments that report on nothing, the copy an adopter actually runs

**What this round was.** Three threads reported back, and most of what they
found was one shape seen from different sides: an instrument answering
confidently about something it had not read. A lint said OK over zero files.
A verifier said "by assertion" about a crash. A copied guard gave no way to
tell it was weeks behind the file it was copied from. Each is fixed here with
its guard in the same commit, and the register gained twenty-one rows, of
which nineteen are decided and two deferred with reasons.

The first finding, R21-1, landed before the rest of the round at `5c8c0c5`
and is recorded here rather than redone. R21-9 to R21-13 and R21-16 landed on
main for the v0.5.2 release, each found by the outside review that held that
tag until it was fixed; this branch is rebased onto that work. R21-17 was
confirmed during that review and is fixed here, after the tag.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R21-1 | high | 6.6 | the maintainer, after the v0.5.1 tag | fixed | `plugin/.claude-plugin/plugin.json` declared `"version": "0.3.0"` through v0.5.0 and v0.5.1. Claude Code keys a plugin update on that string, so v0.5.1's security fix compared 0.3.0 with 0.3.0 and never reached an installed plugin. The version was removed so the commit is the version; `__version__` and the MCP server's `serverInfo.version` became 0.5.2; two tests refuse a pinned manifest version and a version string behind the newest CHANGELOG heading. Six mutants, each red on its intended test. Landed at `5c8c0c5` |
| R21-2 | med | 2.9 | Thread-M's report, reproduced here on an empty directory | fixed | `swallow_lint` and `interpolation_lint` printed OK and exited 0 over paths holding no Python file, including the `src/` they assume with no argument; `conflated_degrade_lint` refused a missing path and then printed OK for a named empty one. A CI step aimed at the wrong directory was green on every run and had read nothing, and the plugin's pre-commit gate repeated it as "swallow_lint OK". All three now exit 2 - the could-not-run code the other guards already use - naming each path and why it held nothing; the gate reports it as skipped in the guard's words; the MCP error leads with the guard's sentence. A class ratchet over every module in the package |
| R21-3 | med | 2.2 | Thread-M's report, reproduced on throwaway repositories | fixed | `verify_guard`'s grader matched `FAILED `, which unittest prints as `FAILED (errors=1)` for a test module that did not import and `FAILED (failures=1)` for a failed assertion. A revert that removed a symbol the test imports was certified "failed by assertion - it discriminates on behaviour" under unittest and graded weak under pytest. unittest is now graded by its own counts; pytest grading is unchanged |
| R21-4 | low | 2.3 | Thread-M's report | fixed | the selfcheck reachability ratchet ran every module as `python -m sutradhar_guards.<module>` only. Adopters run copied files by path, which loads a module with nothing on `sys.path` but its own directory. Both forms worked; one was pinned. All three assertions now run in both forms |
| R21-5 | low | 6.7 | reading the guards' headers | fixed | six guards had `#!/usr/bin/env python3` on line 3, under the license header, where no loader reads it. Run as `./swallow_lint.py --selfcheck` after `chmod +x`, the round-20 copy was handed to a shell, which ran its docstring as commands and exited 2. Moved to line 1; a class test over three shipped directories |
| R21-6 | high | 6.6 | Thread-A and Thread-F, independently | fixed | two adopting trees ran copies of a guard missing an injection detection this repository had added weeks earlier, and nothing in either tree could say which release it held. `bootstrap.sh` now writes `.sutradhar-bootstrap` - release and sha256 per placed file - and `bootstrap.sh --check` reports each current, stale, modified locally or missing, offline, from any checkout; `--track` starts a record in an older tree |
| R21-7 | med | 2.2 | Thread-M's mutation harness | fixed | `verify_guard` certified any red, so a revert that broke a neighbour while the test written for the fix kept passing came back VERIFIED. `--expect <test-id>` now requires every named test among the failures the runner reports; a red elsewhere names what went red; output naming no test is INCONCLUSIVE |
| R21-8 | low | 8.1 | the backflow register | fixed | twenty-one register items arrived this round and nineteen are decided in it: sixteen adopted, three rejected with reasons, two deferred to round 23 with reasons. Five doctrine edits, each inside an existing rule; 49 rules before and after, no id moved |
| R21-9 | high | 2.3 | the outside review of v0.5.2, first pass | fixed | the MCP server's loopback check for `obsgate`'s `metrics` read the host with a pattern of its own that stopped at the first `:`, so `http://localhost:1@169.254.169.254/` read as `localhost` and was allowed, where RFC 3986 reads the host as 169.254.169.254. Refuted before fixing, on Python 3.9.6, 3.12 and 3.13: with no proxy the fetcher never reached that host; with an HTTP proxy the URL reached the proxy intact. The host is now read by the standard parser, user-info is refused, and the URL handed on is rebuilt from the checked parts. A grid of 12,800 spellings and the reviewer's payload through the real server; ten mutants. Landed at `13da8cc` |
| R21-10 | low | 3.7 | the outside review of v0.5.2, first pass | fixed | the version test read only `## vX.Y.Z` headings, so a newer release spelled `## 0.6.0` or `## [0.6.0]` was skipped and stale strings passed; and it never read `CITATION.cff` (0.4.0) or the browser probe's `serverInfo` (0.2.0). Every `## ` heading must now read as a release or be Unreleased, and four version strings must agree with the newest. Landed at `13da8cc` |
| R21-11 | high | 3.6 | the outside review of v0.5.2, second pass | fixed | the loopback check judged the URL while `obsgate` followed redirects, so an allowed loopback server answering 302 sent the fetch to another port, a name, or the metadata address. `obsgate check` and `snapshot` gained `--redirects`, taking `follow` or `refuse`, and the MCP server passes `refuse` unless any host is allowed. Tests count requests at a real target; six mutants. Landed at `9ee22ad` |
| R21-12 | high | 7.2 | the outside review of v0.5.2, second pass | fixed | only `repo` and `metrics` were confined: `obsgate_snapshot` wrote its `out` beside the repository while the plugin README said the server writes nothing, and twelve other path arguments reached the guards unchecked. Every declared path argument is resolved against the directory the guard runs in, symlinks followed, and refused outside the repository; a classification test fails on any tool argument that is neither a confined path nor a reasoned non-path. Seven mutants, one of them the server's own selfcheck. Landed at `9ee22ad` |
| R21-13 | low | 7.2 | the outside review of v0.5.2, second pass | fixed | the plugin README, the hooks design note, and the `Stop` hook's own docstring and comment described the retired author-email gate, or the run-nothing draft that never shipped. Prose, corrected against `verify_before_done.py`; no guard, because a test pinning a sentence would count strings (3.6). Landed at `9ee22ad` |
| R21-14 | med | 2.9 | adding `--expect` (R21-7) | fixed | `verify_guard`'s CLI skipped any argument it did not know, so a typo such as `--gaurd-paths` ran a different verification from the one asked for and still returned a verdict - and would have silently dropped a mistyped `--expect`. A flag with no value raised IndexError and a non-integer `--timeout` raised ValueError, each exiting 1, which is DECORATION's code. Measured before the fix: both exited 1. All are now INCONCLUSIVE, exit 2, naming the argument |
| R21-15 | low | 3.7 | a real `--json` run while testing R21-7 | deferred | `verify_guard` warned that `calc.py` "may be the guard itself" for the guard command `pytest tests/test_calc.py`: `path in guard_cmd` is a bare substring test that runs before the token-boundary regex beside it. `test_guard_collision_warning_does_not_fire_on_substrings` is named for exactly this case and its guard command, `tests/check_real.py`, contains no substring of `calc.py`, so it cannot fail on it. A warning, never a verdict, and not fixed this round |
| R21-16 | high | 2.8 | the outside review of v0.5.2, third pass | fixed | a tool argument could be read as the guard's own option, because the guards read their flags by membership: `paths` of `["--update-baseline", "src"]` made `swallow_lint` rewrite its baseline from inside the loop it holds, and `commit="--help"` made `verify_guard` exit 0 over its usage text and come back VERIFIED. Confinement could not see either. `_string` and `_string_list` now refuse a value beginning with `-`, and `verify_guard`'s verdict is reported only when the JSON it was asked for agrees with its exit code. A class test hands every string and list argument of every tool a flag; seven mutants. Landed at `3f8089f` |
| R21-17 | med | 2.3 | read by this round's agent; confirmed against the skills docs by the maintainer and by the outside review | fixed | both skill wrappers told Claude to read `${CLAUDE_PLUGIN_ROOT}/../agent/skills/<name>.md`, and an installed plugin is copied without `agent/`, so every marketplace user's invocation of either skill reported the file missing. Round 16 recorded that as a deliberate exception to R16-1, and a test pinned the path. This revokes the exception: `plugin/sync_guards.py` copies each canonical body beside its wrapper, byte-identical; the wrappers read the copy; the outside-reference ratchet now covers `SKILL.md`; and a test copies `plugin/` alone, as an install does, and requires every path a wrapper names to exist in the copy |
| R21-18 | low | 6.11 | the outside review of v0.5.2, fourth pass | deferred | through the MCP server, the eight tools without a JSON verdict map exit 1 to a red verdict, and Python exits 1 on an uncaught exception: `swallow_lint` given a baseline of the wrong shape raised `TypeError` and came back `FINDINGS (exit 1)`, `isError: false`, with the traceback in `stderr`. Red is the safe direction and the traceback is attached, so nothing passes that should not, but a guard that crashed has not reported anything, and the word says it has. Deferred to round 22 together with the NUL-byte message below: both are the adapter naming the wrong party (6.8), and both change how every tool's failure is worded, which is a change to make once and with its own review |

## What each register item became

| item | evidence | decision | landed in |
|---|---|---|---|
| B-27 | scar | adopted, **built** | R21-2: three lints refuse an empty scan; the class ratchet |
| B-28 | scar | adopted, **built** | R21-3: unittest graded by its own counts |
| B-29 | practice | adopted, **built** | R21-4: both invocation forms pinned |
| B-30 | practice | adopted | 2.2: verify a layered defence one layer at a time |
| B-31 | practice | adopted, **built** | R21-7: `verify_guard --expect` |
| B-32 | practice | adopted | 4.2: eval independence, a perfect score investigated |
| B-33 | practice | adopted | 4.5: review enforced by absence, no new guard |
| B-34 | practice | adopted, **as a skill** | `agent/skills/robustness-loop.md`: stale bytecode in a manual mutant |
| B-35 | practice | **rejected** | nowhere: a product-shaped server; its lesson is B-30 |
| B-36 | practice | **rejected** | nowhere: the baseline has no per-site identity, and 2.7 asks for a comment at the site |
| B-37 | scar | adopted, **built** | R21-6: the bootstrap record and `--check`, as convergence with B-26 on 6.6 |
| B-38 | scar | adopted | 7.2 gains its scar |
| B-39 | scar | adopted, **as convergence** | 2.9's refusal-rate clause, no text |
| B-40 | scar | adopted, **as convergence** | 5.1 and 2.5, no text |
| B-41 | practice | adopted, **as convergence** | 6.8, no text |
| B-42 | scar | adopted | 6.1's scar extended |
| B-43 | scar | adopted, **as convergence** | 6.7, no text |
| B-44 | practice | adopted, **as convergence** | 3.1, no text; not an 8.2 sentence |
| B-45 | scar | deferred to 23 | one instance of domain statistics |
| B-46 | scar | deferred to 23 | one instance; 7.3 or 2.4 undecided |
| B-47 | practice | **rejected** | nowhere: hygiene with no incident |

`rounds.py docs/rounds/ --backflow docs/backflow.md` reports 47 items: 41
adopted, 4 rejected, 2 deferred, and exits 0.

## R21-2: the exit code, and everyone who reads it

The brief asked for the code this repository already uses for
could-not-check, and to stop if that code meant something else in the three
lints. It does not. `framework_shape`, `ci_step_lint`, `rounds` and
`ownership_lint` all document exit 2 as "the check could not run", and in the
three lints exit 2 already meant an unknown flag - which is the same thing: a
check that did not run. So no partition moved. `obsgate`'s 3 is its own
INCONCLUSIVE verdict and was not the precedent to follow for a lint.

`--update-baseline` refuses too. A floor recorded over nothing is a floor of
nothing, and the next run would gate against it as if it meant something.

Every caller was traced, because a refusal that turns an honest commit red is
the gate being uninstalled by lunchtime (R14-2):

- **The pre-commit gate** mapped exit 2 to an instrument failure - "the hook's
  failure and not a verdict on your code". Nothing in the hook breaks when a
  lint finds no Python, so that sentence named the wrong party (6.8). Exit 2
  now maps to skipped, for all five guards the gate runs, with the guard's
  own last line as the reason. That widens past the three lints on purpose:
  for `rounds`, `framework_shape` and `ownership_lint`, exit 2 is an
  unreadable record, baseline or manifest in the user's repository, which is
  also not the hook's failure. The drill below shows a commit in a repository
  with a swallow baseline and no Python allowed, with the refusal quoted.
- **The MCP server** keeps exit 2 as a JSON-RPC error, because no measurement
  was taken, but its message said "the guard crashed or this server is out of
  date". It now leads with the guard's sentence and carries it as
  `guard_said`. The change is confined to the exit-code mapping in `run_tool`.
- **`ci/guards.yml`** gained a comment on the three steps saying why one can go
  red on a first push and what to change; `bootstrap.sh`'s next steps say the
  same under 2g. `selftest.yml` and `examples/run-the-guards.sh` only run
  selfchecks or scan trees that hold Python, and needed nothing.

**The class ratchet derives its set from code.** It hands every module
`pkgutil` finds in the package only an empty directory, run from inside it, in
both invocation forms, and fails on exit 0 or a line saying OK. A module that
takes no directory refuses the argument; one that does must refuse the scan.
No list of "scanning guards" exists to go stale.

One module is exempt, and the exemption is a decision rather than a
convenience. `budget.py` exits 0 over a design-notes directory that declares
no budget, and prints "no budgets declared under ...". `bootstrap.sh` ships
that directory holding only `TEMPLATE.md`, so refusing it would open every
fresh adopter's CI red over a promise they have not made - the same trade
`ownership_lint` makes for a missing manifest. The exemption carries that
reason and the line it must print, and a second test fails the day `budget`
stops exiting 0, so the entry cannot outlive its truth.

**The first draft of the ratchet was wrong, and the guard it ran said so.** It
planted a `README.md` in the "empty" directory. `framework_shape` counts a
top-level README as framework surface, read it, and said OK over one file -
correctly. A fixture a guard legitimately reads is not nothing to read. The
directory is now empty, and "a repository with no Python" is tested in each
lint's own file, where nothing can be defined per guard.

## R21-3: which unittest reds are weak

Errors and no failures is weak, worded as erroring rather than loading,
because a unittest ERROR is also what a test raising `AttributeError` at run
time produces. Any failure is by assertion, **including a run that also has
errors**; the brief read `_FailedTest` as weak regardless. The decision here
is that an assertion that fired has discriminated, and an import error beside
it does not unsay that, so the grade stays strong and the sentence quotes both
counts. A `_FailedTest` with no summary line and no `AssertionError` is weak.

The first mutation run of this found a gap the tests had: reverting the
errors branch left every flag unchanged, because stripping the summary line
falls through to the generic weak text. The end-to-end cases now pin the
wording as well as the flag, and a runtime `AttributeError` case pins the
branch on its own.

## R21-6: the record, and what it will and will not say

**Name and place.** `.sutradhar-bootstrap` at the target's root, beside
`.sutradhar-owners`: plain tab-separated text, so reading it needs a shell and
nothing else, and a `written-by` line with the release and the checkout's
commit. The release is read from `__version__` with `sed`, because bootstrap
must run where Python does not; a test pins the recorded release to the
package's own `__version__`.

**What `--check` exits.** 0 when nothing is behind, 1 when a file is stale, 2
when it could not check. An edit or a deletion is reported and never fails:
"everything copied is yours to edit" is this framework's promise, and a check
that failed on it would be deleted the first time somebody used the promise.
A tree with no record is "not tracked", exit 0, with the exact `--track`
command, as the brief required.

**What it cannot say, stated in its output.** A file recorded by `--track`
that differed from the checkout is recorded "as found", release unknown:
whether it was an older release or an edit made before tracking cannot be
told, and the output says so rather than guessing. A pre-existing file found
by a normal bootstrap run is recorded only when it is byte-identical to this
checkout, which is proof of where it came from.

**No new file in anyone's tree, and no version header.** The published count
of eighteen guards is unchanged, and every copied file stays byte-identical to
its source. `--check` and `--track` are modes of `bootstrap.sh`.

**No design note.** The mechanism declares no cardinality this repository
can enforce - the file count is whatever bootstrap copies - so a note would
carry no budget for `budget.py` to hold, the reasoning round 19 and 20 applied
to guards of the same size.

Measured on this machine only: macOS, bash 3.2.57, where `sha256sum` is
present and was used. The `shasum` fallback and GNU coreutils on Linux were
not exercised here.

## R21-7: two answers when the named test is not red

When a named test is not among the failures, it has either passed or not run
under that name, and the output decides which can be claimed. If the runner
lists it as passing (`pytest -v`, `unittest -v`), the answer is DECORATION:
the test written for the fix was run and could not see the defect. If the
runner lists no passes (`pytest -q`), the answer is INCONCLUSIVE, because
DECORATION there would claim a pass nobody saw (2.9, 6.9). Both name what did
go red. The brief left the verdict open; this split is the decision.

**Not exposed through the MCP server.** The change there is one argument in
`_argv_verify_guard`, and main owns the argv builders for v0.5.2. It is
recorded as not done rather than half-done.

## R21-8: placements, and the three arguments with the brief

Five doctrine edits, all inside existing rules: sentences in 2.2, 4.2 and 4.5,
a scar extension in 6.1, and the scar 7.2 did not have. Where a lesson only
confirmed a rule already here, it became convergence in the register with no
text (B-39, B-40, B-41, B-43).

- **B-44, "a verdict that changes nothing downstream is a survey".** Every
  wording tried for 8.2 restated 3.1 with control replaced by verdict - an
  output must change something, and something must show that it did. A
  second sentence for one idea is the accretion 8.2 itself names, so it is
  convergence on 3.1. The delete-it half is already 8.2's sentence about a
  thing with a test and no product.
- **B-37 on 6.6**, not 7.2. The stale copy is a question about what is
  running in the adopter's tree, which 6.6 already answers from the running
  copy (B-26); a copied guard is a deployment of it.
- **B-34 as skill text**, not doctrine, as the brief proposed: it is a detail
  of one language's bytecode cache, and 2.2 already says to mutate the line
  that runs. Every in-place mutant in this round ran with a fresh
  `PYTHONPYCACHEPREFIX`.

B-45 sits on 6.6 in the register because 6.6 keeps alerting out of the
doctrine until an incident pays its way in; B-46 sits on 7.3 provisionally.
Both are re-decided at round 23.

## Mutation verification (2.2)

Every mutant was applied to a line that executes, in place, with a fresh
`PYTHONPYCACHEPREFIX`, restored from an in-memory copy, and the restore proven
by sha256 of the file before and after. Line numbers are those at the time of
the run. Each result below is red on the intended test.

| finding | mutant (file:line, change) | red | restore sha256 |
|---|---|---|---|
| R21-5 | `ci_step_lint.py:1`, shebang moved back under the header | `test_every_shebang_is_on_line_one` | `9b9c9bbc…95bfca2` |
| R21-4 | `golden.py:36`, `import json` -> `from sutradhar_guards.ratchet import json` | `test_selfcheck_runs_and_says_so[golden-path]`; the three `-m` cases stayed green | `6ea196ea…aa331296` |
| R21-2 | `swallow_lint.py:356`, `if not py_files:` -> `if False:` | 13 tests incl. the four new CLI cases and `test_a_directory_with_nothing_to_read_is_never_ok[swallow_lint-*]`; `--selfcheck` by path exits 1 | `5ec153d6…ab1e89c7b1` |
| R21-2 | `interpolation_lint.py:522`, the same | 7 incl. both new CLI cases and the ratchet in both forms | `7a77a848…6fbe9b2b7` |
| R21-2 | `conflated_degrade_lint.py:519`, `if not files:` -> `if False:` | 12 incl. the three new cases and the ratchet | `ee797181…0aea32` |
| R21-2 | `precommit_gate.py:189`, `if run.status == H.SKIPPED:` -> `if False:` | `test_a_lint_that_scanned_nothing_is_skipped_never_ok_never_red` (INSTRUMENT-FAILURE) | `46914e94…be3ba6d` |
| R21-2 | `mcp_server.py:881`, `if proc.returncode == 2 and said:` -> `if False:` | `test_a_lint_that_scanned_nothing_says_so_instead_of_blaming_the_server` | `726def7a…d253d4784` |
| R21-3 | `verify_guard.py:464`, `if summaries:` -> `if False:` | `[unittest-symbol]` on its wording, the runtime-error case, the failure-beside-error case | `5f69867f…fcb8b7ffa` |
| R21-3 | `verify_guard.py:473`, `if errors:` -> `if False:` | `[unittest-symbol]` graded strong, the runtime-error case | `5f69867f…fcb8b7ffa` |
| R21-3 | `verify_guard.py:485`, the `_FailedTest` elif -> `elif False:` | `test_a_failed_import_is_weak_even_without_unittest_s_summary_line` | `5f69867f…fcb8b7ffa` |
| R21-6 | `bootstrap.sh:299`, a copied file's record entry skipped | `test_bootstrap_records_every_file_it_copies` | `171c4b99…12bd1bc7` |
| R21-6 | `bootstrap.sh:169`, modified-locally branch -> `elif false` | the stale-versus-modified case and the changed-here case | `171c4b99…12bd1bc7` |
| R21-6 | `bootstrap.sh:201`, stale exit -> `if false` | the stale-versus-modified case and the `--track` case | `171c4b99…12bd1bc7` |
| R21-6 | `bootstrap.sh:122`, no-record branch -> `if false` | `test_an_untracked_tree_is_not_red_and_gets_the_exact_command` | `171c4b99…12bd1bc7` |
| R21-6 | `bootstrap.sh:153`, malformed-row refusal -> `if false` | the malformed-row case | `171c4b99…12bd1bc7` |
| R21-6 | `bootstrap.sh:254`, keep-old-rows -> `&& 0` | `test_rerunning_bootstrap_keeps_the_rows_it_did_not_replace` | `171c4b99…12bd1bc7` |
| R21-6 | `bootstrap.sh:277`, `--track` records `unknown` -> `$VERSION` | the `--track` case | `171c4b99…12bd1bc7` |
| R21-14 | `verify_guard.py:1016`, unknown-argument refusal -> `if False:` | two parametrised CLI cases | `d9922a37…b21d55a5b` |
| R21-14 | `verify_guard.py:1018`, missing-value refusal -> `if False:` | the missing-value case | `d9922a37…b21d55a5b` |
| R21-14 | `verify_guard.py:1033`, `except ValueError` -> `except KeyError` | the `--timeout` case | `d9922a37…b21d55a5b` |
| R21-7 | `verify_guard.py:768`, `missing = []` | both DECORATION cases, the INCONCLUSIVE case, the CLI case | `521f7a23…779cfdb4a` |
| R21-7 | `verify_guard.py:757`, `if not red_ids:` -> `if False:` | `test_a_red_that_names_no_test_is_inconclusive_never_verified` | `521f7a23…779cfdb4a` |
| R21-7 | `verify_guard.py:773`, `if seen_passing:` -> `if True:` | `test_a_red_elsewhere_with_the_named_test_not_seen_is_inconclusive` | `521f7a23…779cfdb4a` |
| R21-7 | `verify_guard.py:548`, unittest reds appended to passes | three unittest VERIFIED cases and the id-reader case | `521f7a23…779cfdb4a` |
| R21-7 | `verify_guard.py:1166`, `expected.append` -> `expected.clear()` | `test_expect_reaches_the_verdict_through_the_cli` | `521f7a23…779cfdb4a` |

| R21-17 | `plugin/skills/robustness-loop/SKILL.md`, the path back to `${CLAUDE_PLUGIN_ROOT}/../agent/skills/` | `test_every_path_a_skill_names_exists_in_an_installed_copy`, the outside-reference ratchet, `test_every_canonical_skill_has_a_plugin_wrapper` | matched |
| R21-17 | `plugin/sync_guards.py`, `"ops-drill.md"` dropped from `SKILLS` and its bundled copy deleted | the installed-copy test, the wrapper ratchet, the drift test | matched, deleted file restored |
| R21-17 | `plugin/skills/ops-drill/ops-drill.md`, one heading edited so the copy drifts | the wrapper ratchet, `test_sync_guards_check_agrees_with_this_file` | matched |
| R21-17 | `plugin/sync_guards.py`, `_pairs` returns the guards only | `test_sync_guards_sees_a_drifted_skill_body` | matched |

R21-8 changed text and no mechanism, so it has no line to mutate; the register
gate that holds it carries its own planted overdue item and ran green.

R21-9 to R21-12 and R21-16 were mutation-verified on main before the v0.5.2
tag, in the same discipline - a line that runs, a fresh bytecode cache, a
sha256-checked restore - and each commit message lists its mutants: `13da8cc`
(ten, for R21-9 and R21-10), `9ee22ad` (thirteen, for R21-11 and R21-12),
`3f8089f` (seven, for R21-16). R21-13 is prose and has none.

## Drills

**Cold bootstrap**, into a fresh `git init` directory: 35 files copied, and
all 15 copied Python guards' `--selfcheck` exit 0 when run by path.
`bootstrap.sh --check` on the fresh tree reports 35 current and exits 0. The
next steps read correctly, and followed literally in a tree with no `src/`,
steps 1, 2 and 2g exit 2 with "nothing was scanned: src (does not exist)" -
which is what the new parenthesis under 2g tells the reader to expect.

**The pre-commit gate**, driven with a real PreToolUse payload for
`git commit` in a repository holding no Python file and a
`swallow_baseline.json`: the hook exits 0, emits no deny decision, and reports
"swallow_lint skipped (could not check: [swallow-lint] nothing was scanned:
... holds no .py file ...)". Not blocked.

## Measured, not estimated

| Number | Before (`5c8c0c5`) | After |
|---|---|---|
| tests | 816 | **972**, rebased onto the v0.5.2 tag (953 before the rebase) |
| guard modules | 18 | 18 |
| guard programs bundled in the plugin | 10 | 10 |
| skill bodies carried in the plugin | 0 | **2** |
| doctrine rules | 49 | 49 |
| register items | 26 | **47** |
| register items decided this round | - | 19 (16 adopted, 3 rejected), 2 deferred |
| planted defects the demo catches | 7 of 7 | 7 of 7 |

The suite ran on Python 3.9.6 on macOS. Python 3.13 and a Linux runner were
not run in this round; CI was not run, because nothing was pushed.

## What was ruled out, and what is not done (7.4)

- **The plugin README's sentence about skipped guards.** The R21-2 commit
  added it to "What it will and will not do"; main is rewriting that section
  for v0.5.2, so a follow-up commit took it back out. The behaviour is stated
  in the hooks design note, the gate's docstring and CHANGELOG. The README
  sentence is owed after the rebase.
- **`--expect` through the MCP server.** Not done; main owns the argv builders.
- **R21-15**, the collision warning's substring test. Deferred: a warning and
  not a verdict, found late, and fixing it well means rewriting the test that
  claims to cover it.
- **Refusing a missing design-notes directory in `budget.py`.** It exits 0 with
  "no design notes at ... - nothing to check". Left alone: an adopter who took
  the CI layer and not the docs layer would go red for it, and it prints what
  it did not do.
- **A design note for R21-6.** No enforceable budget; see above.
- **The skill wrappers' `../` path**, first read here as an observation and
  not filed until it was checked (6.4), was confirmed against the skills docs,
  which substitute `${CLAUDE_PLUGIN_ROOT}` into skill text, and against the
  marketplace docs, which copy a plugin without its surroundings. It is fixed
  as R21-17, after the v0.5.2 tag rather than in it: usability, not security,
  and unchanged since v0.5.0.
- **A NUL byte in an MCP path argument** surfaces as -32603, "this server
  raised ValueError", which is honest that nothing ran and wrong about whose
  failure it is (6.8). Found by the outside review; not fixed in the release,
  and not yet here.

## Guards touched

`swallow_lint.py`, `interpolation_lint.py`, `conflated_degrade_lint.py`
(R21-2, R21-5), `ci_step_lint.py`, `framework_shape.py`, `ownership_lint.py`
(R21-5), `verify_guard.py` (R21-3, R21-7, R21-14), `mcp_server.py` (R21-2,
the exit-code message only), `plugin/guards/` (re-synced),
`plugin/scripts/precommit_gate.py` (R21-2), `bootstrap.sh` (R21-2, R21-6),
`ci/guards.yml`, `.github/workflows/selftest.yml`, `DOCTRINE.md` (2.2, 4.2,
4.5, 6.1, 7.2 - text only), `docs/backflow.md`,
`agent/skills/robustness-loop.md`, both design notes' partition tables,
`README.md`, `python/README.md`, `docs/adoption.md` and `CHANGELOG.md`.

On main for v0.5.2, before this branch was rebased: `mcp_server.py` (R21-9,
R21-11, R21-12, R21-16), `obsgate.py` (R21-11), `CITATION.cff` and
`js/probe/mcp.mjs` (R21-10), `verify_before_done.py`'s docstring and comment
(R21-13), `SECURITY.md` and `plugin/README.md`. After the tag, here:
`plugin/sync_guards.py`, both skill wrappers and the copies beside them
(R21-17).

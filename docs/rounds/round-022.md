# Round 22 - 2026-09-20

Lenses: the demo's denominator, the scorer for the improvement loop

**What this round was.** The mechanism for the framework's own improvement
loop: a defect corpus with a scorer that cannot be gamed by deleting cases
or by counting its own iterations. Two findings fell out of reading the
demo while designing it - the "7 of 7" is a loop counter, and every planted
defect is declared twice in two places that disagree. Both are fixed here
with the mechanism in the same commit. Two more findings are deferred with
their open cases named, so the deferral is a pointer rather than a shrug.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R22-1 | high | 3.7 | reading run-the-guards.sh while designing the corpus | fixed | The demo's "7 of 7" is a loop counter, not a declared total: deleting a whole block yields "6 of 6" and exit 0, and only a string pin in test_examples.py holds the number. The corpus takes its denominator from the manifest set, and the demo now declares EXPECTED=7 and refuses a run whose count differs; test_the_runner_fails_when_a_check_is_deleted pins it and goes red on the old tail with 6 of 6. |
| R22-2 | med | 8.2 | the same read | fixed | Each planted defect is declared twice, in the source comment and in the script, and the two numberings disagree. A manifest removes the second copy: one file per case, twins and prose together. |
| R22-3 | med | 6.3 | auditing ci_step_lint's scope | deferred | No guard checks a workflow for a pipe that swallows an exit code; 6.3 is convention-only. Seeded as an open corpus case (ci-pipe-swallows-exit-code) in the wave-1 batch. |
| R22-4 | low | 1.1 | reading budget.py's enforcement detector | deferred | The budget gate proves a test MENTIONS an id, not that it asserts. Re-states R1-8 from the corpus side; the corpus budget test asserts genuinely, the gate itself stays text-match until a round pays for more. |
| R22-5 | high | 6.7 | the maintainer's review of the phase commits | fixed | The improvement-round skill's first command ran scripts/rounds.py and its case command ran scripts/corpus.py. Neither path exists in this repository, where the Monday round runs; scripts/ is the layout bootstrap creates in an adopter's tree. The scheduled round would have died at its first step. Every command now uses this repository's paths, and each was run before being written down. |
| R22-6 | high | 2.2 | the same review | fixed | The skill ran verify_guard --commit HEAD in the gate phase and only committed in the phase after, so the gate would have reverted the previous commit and verified nothing about the candidate. The round now commits on its branch first, runs the gate against that commit, and amends the message with the evidence. It also says that reverting a brand-new module only yields an import-error red, which verify_guard grades weak, so the detection line must be weakened too. |
| R22-7 | med | 7.2 | the same review | fixed | The plugin wrapper told the agent the corpus was available as an MCP tool. It is not one: mcp_server.py never mentions it. A documented capability that exists in no code. The wrapper is removed with R22-8. |
| R22-8 | med | 2.2 | the same review | fixed | The skill shipped to adopters through the plugin and bootstrap, while corpus.py deliberately ships through neither. Every adopter would have received a loop whose only scorer is absent from their tree, the R20-4 shape aimed at a skill. The first fix kept the skill in agent/skills with no wrapper, and the class ratchet test_every_canonical_skill_has_a_plugin_wrapper refused it: everything in agent/skills ships. Rather than carve an exception into the ratchet, the skill moved to corpus/improvement-round.md beside the scorer it drives; the two join the copy set together, and the ratchet will demand the wrapper then. |
| R22-9 | low | 6.10 | timing the real corpus during the review | deferred | The defect-corpus budget measures 60 synthetic cases of the cheapest guard (4.5 s). The real corpus, which CI runs, mixes every guard and took 24.4 s for 53 cases on the same laptop. Only the CI job timeout bounds it. The design note now says what the envelope does and does not bind. |
| R22-10 | low | 7.3 | the same review | fixed | The phase-3 ownership manifest was committed at the repository root, already stale (it named a case file that does not exist). Its presence alone arms the precommit gate's ownership check for anyone who sets SUTRADHAR_OWNER. Removed; a manifest for parallel agents belongs in their worktrees, not in the shipped tree. |
| R22-11 | low | 5.1 | the same review | fixed | The changelog said 11 rules covered; the run printed 12, and 11 plus 11 excluded plus 26 banked does not make 49. Corrected from the witnessed output. |
| R22-12 | low | 1.1 | the full local suite during the review | deferred | test_precommit_gate_holds_its_declared_envelope breached at 9,149 ms against 5,000 ms in a loaded full run. Ruled out as this change set's regression: the same test on main ran 4.0 to 10.9 s isolated, against 5.8 to 9.4 s on the branch. The envelope is tight for a laptop under load; not widened on local noise, and CI is the arbiter. |

## Corrected premises

- **"The demo counts its defects."** It counts its own blocks. A denominator
  that comes from control flow is a promise the code makes to itself; the
  corpus counts files on disk, which is a promise the tree can check.
- **"Mentioning a budget id enforces it."** The gate matches text, so a test
  that names the id without asserting anything passes it. The corpus budget
  test runs the work at the declared N inside the envelope - mention plus
  measurement, because the gate only checks the mention.

## What the review changed

- **The backfill went deep, not wide, and the design is why.** A case
  had to name a guard in the registry, and most rules still uncovered have
  no guard. So the waves added variants on guards that already had cases,
  and banked each guardless rule in `corpus/uncovered.json` with the case
  idea it waits for. That is the right resolution: authoring that case is
  phase 2 of the improvement round itself. The file's reasons are
  relabelled from "wave 3" to "loop queue", because no wave is coming;
  the loop is.
- **R22-1 was marked fixed while the demo still had the defect.** The new
  scorer did not have it; the demo did. A `fixed` status keeps a finding
  out of the residual register, so a wrong one silently drops a live
  defect from the backlog. Fixed in the demo rather than reworded.

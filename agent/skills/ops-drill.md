# Skill: ops drill - operate the system, don't read it

A repeatable procedure for finding the defects that code review structurally
cannot see. The empirical record behind it: almost every serious operational
defect on the codebase this framework distills was found by OPERATING the
system, not reading it - the backup that restored zero rows, the
root-owned data directory that silently killed a persistence path, the
architecture-dependent build, the tenant fix that was half dead in the
running app. Dozens of adversarial code-reading rounds moved operational
readiness less than three drills did.

A drill is not a demo. Its job is to make the docs and scripts fail in
front of you, cheaply, before a customer makes them fail expensively.

## The four drill types

| Drill | What is under test | Pass looks like |
|---|---|---|
| Cold-start install | The install runbook, followed verbatim on a clean host | A running, healthy stack from docs alone, with every stumble logged |
| Backup/restore reconciliation | The backup and restore scripts | Restore into a scratch stack; row counts and record counts diff clean against the source; health checks green |
| Unattended soak | The running stack over hours or days | No drift, no leak, no silent job death; gaps in observation reported as gaps |
| Upgrade in place | The upgrade procedure | vN to vN+1 on a stack carrying data; regression gates green after |

## Ground rules

1. **Written artifacts only.** The drill follows the doc under test
   verbatim. Institutional memory may answer questions only with "log it
   and keep going". Every place the doc misleads becomes a row in the
   deviation log AND a doc-fix commit the same day. An operator's clever
   workaround goes INTO the doc so the next operator does not need to be
   clever.
2. **Gates are command-verifiable, never vibes.** Each gate has a time
   budget and a pass check that is a command with an exit code or a count
   that must match. Over 2x budget: stop, log the blocker verbatim, move to
   the next independent gate. Unreached gates record "not-reached", never
   silently skipped.
3. **Exit-code discipline in every harness you write.** Never pipe a build
   or test through anything that swallows `$?` (a drill's own `| tail`
   once reported a failed build as success). A truncated run reports as
   truncated. Measure - row counts, RSS, exit codes - never eyeball.
4. **Verify a finding refutes the null before filing it.** Prove your test
   itself is valid first (`docker kill` suppresses restart policies BY
   DESIGN; crash PID 1 inside the container instead). A false finding costs
   more trust than no finding.
5. **Restore outranks everything.** A backup that has not been reconciled
   (restored into a scratch stack, counts diffed against the source, health
   green) is cosmetics. No real data rides on an unreconciled restore
   path. The precedent: a plain `psql < dump` restore aborted at the
   catalog and left 25 tables with zero rows; the dump tool had warned,
   nobody had checked.
6. **Protect the neighbors.** On a shared host, scrub selectively; never
   global-prune volumes; verify other projects' containers survived
   afterward.
7. **State the fidelity honestly.** A drill run by the author on a scrubbed
   shared machine is the WEAKER form and scores accordingly. A sleeping
   laptop is not elapsed service time; report observed gaps, never assume
   continuity. The strong form is a second operator on a clean host.
8. **Gate the observability floor before the soak, not after** (doctrine
   6.6). A soak is only as good as the surfaces watching it: four hours of
   "no errors" from an endpoint serving an empty 200 is four hours of no
   information reported as a clean run. Run the floor gate first, and
   treat its verdict as the drill's own precondition:

   ```bash
   python scripts/obsgate.py --metrics http://localhost:9090/metrics \
                             --floor obs_floor.json
   ```

   Exit 0 = WITNESSED, the surfaces are live and within cardinality caps.
   Exit 1 = UNWITNESSED, a surface is missing or empty - fix that before
   the drill, because every observation after it is unfounded. Exit 3 =
   INCONCLUSIVE, the endpoint could not be read at all, which is never a
   pass. A drill whose floor gate is UNWITNESSED records "not-reached",
   not "green".

## The output

1. The deviation log (the primary artifact), appended live, one row per
   stumble, quoting the doc line that misled.
2. Doc-fix commits, same day, one per deviation.
3. A run record: date, fidelity form, per-gate times, defect table with fix
   commits, honest scoring.
4. Readiness scores move ONLY as far as the fidelity form allows.

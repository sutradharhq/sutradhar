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

## The shape of a boot: one layer at a time, in dependency order

The table above says WHAT each drill puts under test. This says how to boot,
because "start the stack and check it is healthy" is the instruction that
produces a demo. It is runtime-agnostic on purpose: the layers below are
roles, not products, and every command in it is yours.

**1. Write the dependency order down before starting anything.** Not the
order your compose file lists, not the order things came up in last time:
the order in which each layer cannot do its job until the one below it
ANSWERS. A typical spine, bottom first - delete the rows you do not have,
add the ones you do:

| # | Layer | It has answered when |
|---|---|---|
| 1 | persistence | it accepts a connection **and** a trivial read returns the row you put there |
| 2 | schema / migrations | the tool reports the version you expect, and a table the app needs exists and is populated |
| 3 | caches, queues, brokers | a value written through the real client reads back through it |
| 4 | the application | it serves a request that touches layer 1, not a static readiness route |
| 5 | workers and schedulers | a job it owns has **fired and produced an output count** (6.6 - a run that succeeds and produces nothing is a failure unless zero was declared) |
| 6 | the edge: proxy, gateway, load balancer, CDN | it routes to the application rather than to its own error page |
| 7 | the surface a person uses | the page or client renders real data, from a cold cache, as an unprivileged user |

**2. Boot one layer, then stop and assert. Then the next.** Booting
everything at once and checking at the end tells you the stack works; it
cannot tell you which layer was ready when. Half the defects this drill
exists to find live in that gap, and they are invisible once everything is
up.

**3. Assert what an OPERATOR would see, not what the code returns.** The
distinction is the whole method:

| Not this | This |
|---|---|
| the app's own health route says ok | a query a person would run returns the row a person expects |
| the container is `running` | the log line that only prints after the connection is established has printed |
| the process did not exit | the metric it exports has a value, and the value moved when you acted |
| the deploy tool reported success | the version the deployment serves about itself is the one you deployed (6.6) |

A health endpoint is written by the same code that is broken, and it will
report itself healthy while the thing behind it is not. The operator's view
is the one that outlives the deploy, so it is the one that counts.

**4. The defect class to hunt is a layer that started before its dependency
answered.** It is the commonest thing a dependency-ordered boot finds, and
none of its shapes look like a failure from inside:

- a pool that opened while the store was still starting, cached the
  refusal, and serves every later call from a poisoned connection;
- a worker that retried its broker silently and forever, so the queue is
  reachable, the worker is `running`, and nothing is consumed;
- an edge that came up first, cached its own error page, and now serves a
  fast, confident 200 that contains it;
- a migration that ran against a schema not yet created, exited 0 on "no
  work to do", and left the app one table short.

Hunt it deliberately, do not wait to be lucky:

- boot the layers in the WRONG order once, on purpose, and record what the
  upper layer says about it. If it says the same thing it says when
  everything is fine, that is a finding, and it is 1.4 and 2.4 - the
  failure story that reads identical to success;
- with everything up, take one dependency away and watch the layer above.
  Prove the test refutes the null first (ground rule 4): stopping the
  process is not the same event as the network going away, and a restart
  policy will hide one of them from you.

**5. Every layer gate is a command with an exit code, and a time budget.**
No layer is "up" because it looked up. Write the gates before you boot, in
a table you fill in as you go - and a layer whose gate you did not reach is
`not-reached`, never blank and never green:

```
LAYER            GATE (command)                    BUDGET   ACTUAL   VERDICT
1 persistence    <read back a known row>           30s      12s      pass
2 migrations     <report version> = <expected>     60s      41s      pass
...
```

Ground rule 3 applies to every line of it: never pipe a gate through
anything that swallows `$?`, and never read the tail of a log as a verdict.

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

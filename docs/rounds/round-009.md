# Round 9 - 2026-08-18

Lenses: publication, provenance, documentation discipline

**What this round was.** The preparation to make this repository public — and
the documentation-discipline gap that preparation exposed. Recorded because
going public is the most consequential change this repo has made, and because
the framework nearly shipped a violation of its own rules (5.1, 7.4) on its own
front page. The flip itself is a maintainer action; this records the decision,
the method, and what the method taught.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R9-1 | high | - | publication postmortem | fixed | a history rewrite does NOT scrub a hosting platform: GitHub keeps `refs/pull/N/head` permanently, and a force-push cannot remove them. Two merged PRs were verified to carry the pre-scrub provenance commit, so a force-push would have left scrubbed content retrievable via the PR refs. The clean path is archive-and-recreate the repo from scrubbed history, not force-push - verify platform-side refs, not only git history |
| R9-2 | med | 7.4 | going-public review | deferred | the decision to publish, the framework/product split, and the plan behind them were made with no decision record in any repository; the doctrine has no Documentation section; 7.4, the round records, and 5.1 went unapplied to the framework's own most consequential work until this round |
| R7-2 | high | 5.1 | going-public review | fixed | the README's provenance section claimed the framework rested on "one codebase, a sample size of one" - filed wrong in round 7, and contradicting the anonymised round-007 which records a family of independent builds. Corrected before the flip: the specific ratios are labelled as one deep build record, the doctrine's evidence base as the family, no project named |

## Corrected premises

- **"A git history rewrite scrubs the repository."** It scrubs the *history*,
  not the *platform*. `git filter-repo` cleaned every reachable blob and commit
  message, and `main` verified clean - but GitHub's pull-request refs sit
  outside the ref namespace a force-push can reach, and two of them still
  carried the pre-scrub content. The instrument (a clean `git log`) agreed with
  the hypothesis, so the looking almost stopped there; the surface that carried
  the consequence (the public PR pages) disagreed. That is the round-3 class
  (verify the surface that carries the consequence, doctrine 6.6) recurring in
  the publication path, and it is why the scrub verification now includes
  `git ls-remote 'refs/pull/*'`, not only local refs.
- **"We document; the discipline is covered."** The repo carries a doctrine,
  round records, a changelog, and design notes, and still had no home for a
  *decision* - the why behind a course change and what it ruled out (7.4). The
  largest course change in the project's life was drafted in an un-versioned
  scratch file. A framework that tells its adopters to record what they ruled
  out did not record its own biggest ruling. That is R9-2, and it is deferred
  rather than fixed because the fix is a doctrine section (a Documentation
  discipline: decision records, staleness gating, one home per fact), not a
  ten-minute edit - and section 8.1 says a rule enters with the incident that
  paid for it. This round is that incident.

## Harness gotchas

- The provenance correction (R7-2) had to reconcile two surfaces that
  disagreed: the README said "one codebase" while round-007 said "ten
  independent builds". Publishing either alone would have been fine;
  publishing both would have shipped a repo that contradicts itself on the
  fact it most wants trusted. One-home-per-fact is the missing rule under
  R9-2, felt here directly.
- What was published is the scrubbed history: the contributing builds are
  referred to anonymously, the specific ratios are pinned to one deep build,
  and no project is named. The mapping from the anonymous labels to real
  builds is kept only in a private record, never in this repository.

## Stop decision (doctrine 8.3)

CONTINUE - one HIGH this round (R9-1), so no two consecutive quiet rounds.

The work this round leaves open is R9-2: give the doctrine a Documentation
section, or at least a decision-record artifact, so the next consequential
ruling has a home that is not a scratch file. It is the same gap round 6
recorded from the outside (a framework with no decision-record format, unlike
the outside repo it read), now paid for from the inside. That is 8.1 working:
the rule will enter when it is written, with this round as its scar.

# Round 11 - 2026-08-24

Lenses: attribution audit, hosting-platform boundary, cross-repo verification

**What this round was.** A request to confirm Claude was removed as a
contributor turned up a discrepancy: the GitHub UI showed a "claude"
contributor on a repository this session believed fully scrubbed. Checked
directly against all four repositories in this framework's family rather
than trusted from memory, because "we already fixed that" is exactly the
claim doctrine 7.2 says to verify against the tree.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R11-1 | med | 6.4 | direct audit of all four repos, prompted by a UI screenshot | fixed | GitHub's plain contributors REST API is author-only and reported clean everywhere, which is the check this session had relied on; the repo homepage's Contributors SIDEBAR widget additionally parses `Co-Authored-By` trailers and resolves them to accounts, across every ref the platform hosts, not just the default branch. Two instruments answering the same question disagreed, and the API was trusted because it was the one already in hand - exactly the "the looking stopped because the proxy agreed" failure the doctrine names |
| R11-2 | low | - | same audit | closed | `sutradharhq/sutradhar-internal` (the archived private repo, pre-dating this session's scrub) permanently hosts four of its original nine PRs' pre-scrub commits via `refs/pull/{1,2,3,4}/head`, each carrying `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` from before the "stop adding the trailer" instruction took effect mid-session. R9-1 already established that a hosting platform's PR refs cannot be scrubbed by any git or API operation; this is that same limit, hit a second time, on a different surface (the UI-only contributor graph rather than a directly-cloned ref) |

## Corrected premises

- **"The contributors API is the check."** It answers "who authored a
  commit," not "who does this repository publicly credit." A hosting
  platform can carry a second, UI-only computation of the same-sounding
  question with a different, wider definition, and the two will disagree
  exactly where it matters - a co-author trailer nobody scrubbed. Checking
  one endpoint and generalising to "attribution is clean" was unearned;
  the actual check needed both the API and the rendered page, which is a
  repeat of 6.6's point (a claim is worth what the surface that witnessed
  it is worth) aimed at a documentation claim instead of a runtime one.

## Harness gotchas

- Confirmed clean, by the wider (UI-equivalent) definition, not just the
  API: `sutradharhq/sutradhar` (the live public repo - zero PRs were ever
  opened against it, so it has no permanent PR-ref surface to carry
  anything forward), `varunmundra5-stack/sutradhar` (the personal fork - no
  PRs of its own), `sutradharhq/ledger` (no PRs at all).
- `sutradhar-internal` was deliberately left as-is on the maintainer's
  decision: deleting it would remove the residual attribution but also
  permanently destroys the nine PRs' original history and discussion, which
  archiving (rather than deleting) it was meant to preserve in the first
  place. Recorded here so a future session does not re-discover this as a
  surprise and re-litigate a decision already made.

## Stop decision

CONTINUE - R11-1 is a real gap in this session's own verification method,
med severity on the instrument-trust axis (6.7) even though its practical
consequence (R11-2) was accepted as-is. The next round should not re-audit
this; the residual is understood, bounded to one private repo, and closed
by decision rather than by mechanism.

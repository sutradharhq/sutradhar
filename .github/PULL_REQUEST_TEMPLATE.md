<!-- Sutradhar holds this repo to its own doctrine. The checklist is short and
     load-bearing; please do not check a box you did not actually do. -->

## What this changes

Briefly: the defect or gap, and the fix.

## The scar (for a new rule or guard)

If this adds or changes a doctrine rule: what incident paid for it? A rule
without an incident is not ready (doctrine 8.1).

## Checklist

- [ ] A fix ships with a guard in the same commit (2.1) — a class ratchet where possible.
- [ ] The guard was **shown to fail**: reverting the fix turns it red (2.2). I ran it.
- [ ] `--selfcheck` on any guard I touched passes, and I extended it if I changed behavior.
- [ ] `python sutradhar_guards/framework_only.py .` passes — no new dependency, stdlib only.
- [ ] `python -m pytest tests/ -q` passes.
- [ ] `python sutradhar_guards/rounds.py ../docs/rounds/ --check` passes (if I touched docs/rounds).
- [ ] Docs updated in the same change (README caption, the tool's docstring, the doctrine).

## Not required

You do not need to sign a CLA or match a house style beyond what the checks
enforce. If you are only *using* Sutradhar, you do not need to send a PR at all.

---
name: Adoption report
about: You ran Sutradhar on a codebase that is not ours. Tell us what happened — this is the most valuable issue you can open.
title: "[adoption] "
labels: adoption-report
---

<!-- Field evidence is the framework's binding constraint (doctrine 8.4). A
     single honest report of what happened on a real, different codebase is
     worth more than a feature request. Thank you for filing one. -->

## The codebase (as much as you can share)

- Stack / language:
- Rough size (files, or lines):
- Built by agents, humans, or both:

## What you turned on

Which guards / pieces did you copy in (swallow_lint, ratchet, budget,
verify_guard, the probe, uiGuards, the agent rules, …)?

## What it caught

Real defects the guards surfaced. Even one is worth recording.

## Where it cried wolf

False positives, noisy checks, anything that made you want to uninstall it. We
would rather hear this than not.

## Where it was silent but should not have been

A defect it missed, or a check that passed when it should have failed. This is
the most important box.

## Anything else

Rough edges in the docs, the bootstrap, the demo, the naming — whatever stood
out.

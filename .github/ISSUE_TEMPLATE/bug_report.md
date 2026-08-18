---
name: Bug report
about: A guard, the probe, the bootstrap, or the example behaves wrong
title: "[bug] "
labels: bug
---

## Which piece

File and version (the tag or commit you copied in):

## What it does vs. what it should do

<!-- The security-grade version of this: a guard that PASSES when it should
     FAIL. If you can show a guard accepting a known-bad input, say so — that
     is exactly the defect class this framework exists to catch. -->

## Minimal reproduction

The smallest input / command that shows it. If it is a guard, the known-good
and known-bad inputs (the pair) are ideal.

## Environment

- OS:
- Python version (`python --version`) or Node version, as relevant:

## Selfcheck

Does `python sutradhar_guards/<tool>.py --selfcheck` pass or fail on your
machine?

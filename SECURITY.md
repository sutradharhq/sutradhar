# Security

## The short version

Sutradhar is **copy-in and dependency-free**. There is no package to install,
no runtime, and no service. The Python guards import the standard library only;
the browser probe and Cypress guards are zero-dependency too. This is enforced,
not just claimed — `python/sutradhar_guards/framework_only.py` fails the build
if any shipped guard reaches outside the standard library or if a dependency
manifest appears in the framework surface.

The practical consequence for your supply chain: **there is nothing here to
compromise on your behalf.** No transitive dependencies, no post-install
scripts, no network calls, no telemetry. You can read every line that will run
in your CI in a single sitting, and you should — the whole point of copy-in is
that the code lives in your tree, under your review, pinned to the tag you took.

## Reporting a vulnerability

If you find a security issue in a guard, the probe, or the example app, please
report it privately rather than opening a public issue:

- Preferred: open a **GitHub private security advisory** on this repository
  (Security → Report a vulnerability).
- Include: the file and version (tag or commit) you took, what the guard does
  versus what it should do, and a minimal reproduction if you have one.

Because the toolkit runs inside your own CI over your own code, the realistic
threat is a guard that **passes when it should fail** — a check that is
decoration. That is the exact defect class this framework exists to catch, so
we treat "this guard cannot actually fail" as a security-grade report, not a
cosmetic one, and every guard ships with a `--selfcheck` and mutation-verified
tests precisely to keep that from happening. If you can show a guard passing a
known-bad input, that is a finding we want.

## Scope

In scope: the guards under `python/sutradhar_guards/`, the probe under
`js/probe/`, the Cypress guards under `js/cypress/`, the bootstrap script, and
the worked example. Out of scope: your own code, your CI configuration, and any
dependency you add on top of the copy-in files (which is now your supply chain,
not ours).

## Response

This is a small, maintainer-run project. We aim to acknowledge a report within
a few days and to fix a confirmed decoration-class or code-execution issue in
the next tagged release, with the fix shipping — per our own doctrine — beside
a guard that proves the defect fails loudly from then on.

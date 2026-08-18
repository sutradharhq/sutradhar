# Contributing

Sutradhar is a framework built from scars: every rule in the doctrine entered
with a real defect that paid for it, and every guard ships with proof it can
fail. Contributions are held to the same standard the framework holds your
code to. That is the whole product; please help keep it honest.

## The most valuable contribution: a field report

The framework's binding constraint is outside evidence. It was distilled from
one family of builds, and rule 8.4 says one mind shares blind spots with
itself. **If you run these guards on a codebase that is not ours, tell us what
happened** — what a guard caught, where it cried wolf, where it was silent when
it should not have been. Open an *adoption report* issue. A single honest
field report is worth more than a feature.

## If you change a guard or add one

The doctrine applies to this repo first:

- **A fix ships with a guard in the same commit** (2.1). Prefer a class ratchet
  over a point test.
- **Prove the guard can fail** (2.2). Revert your fix and watch the test go
  red; a guard never shown to fail is decoration. Every guard also carries a
  `--selfcheck` that plants a known-bad case — extend it, don't skip it.
- **Stdlib only.** The guards take no dependencies; `framework_only.py` fails
  the build if one appears. A new tool must pass its own gate.
- **A new doctrine rule needs an incident.** Do not add a rule because it sounds
  wise (8.1). Bring the scar, or propose it in a Discussion first.

## Before you open a PR

Run the checks the CI runs (from `python/`):

```bash
python -m pytest tests/ -q
python sutradhar_guards/framework_only.py .
python sutradhar_guards/rounds.py ../docs/rounds/ --check
```

and the guard selfchecks you touched (`python sutradhar_guards/<tool>.py
--selfcheck`). The PR template lists the full checklist.

## Adopting the framework, not changing it

If you are here to *use* Sutradhar, you do not need to contribute anything —
copy the pieces in with `bootstrap.sh` and edit them freely in your own tree.
Everything is copy-in and yours to change. Upstream contributions are welcome
but never required to use it.

## Scope

Sutradhar is a framework, not a product: pre-deploy, copy-in, stdlib. See
[docs/design/scope-framework-only.md](docs/design/scope-framework-only.md).
Proposals for after-deploy runtime features (observability services, hosted
records) are out of scope for this repository by design, and the gate enforces
it.

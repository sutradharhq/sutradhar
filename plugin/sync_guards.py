#!/usr/bin/env python3
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Copy the guards this plugin runs into `plugin/guards/`.

A maintainer tool, run from a checkout. The plugin itself never calls it.

## Why there is a copy at all

Round 15 ruled a copy out, and the reason was good: one server, one version,
because the first time a copy and its source disagreed the copy would win
silently. What that reasoning did not know is that **Claude Code copies an
installed plugin into `~/.claude/plugins/cache`, and files outside the
plugin directory are not copied** - the docs say so outright: copied plugins
cannot reference files outside their directory using paths like
`../shared-utils`, because those files will not be there.

So `plugin/.mcp.json` pointing at `${CLAUDE_PLUGIN_ROOT}/../python/...` was
not a lighter-weight alternative to copying. It was a plugin that worked
only in the layout it was built in - a checkout - and would have failed the
first time anyone installed it from a marketplace (R16-1).

The round-15 argument still holds, so it is answered rather than dropped:
the copies exist, and `python/tests/test_plugin_bundle.py` fails the build
the moment one of them differs from its source by a single byte. Two
answers to "what does `verify_guard` do" are only dangerous while nothing
compares them.

    python3 plugin/sync_guards.py            # copy source -> bundle
    python3 plugin/sync_guards.py --check    # exit 1 if they differ

`--check` is what a human runs; the test is what makes it non-optional.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

#: The single explicit list. Not a glob over the source directory: a guard
#: this plugin does not run has no business being shipped inside it, and a
#: glob would ship whatever landed next door. `test_plugin_bundle.py`
#: derives the set of scripts the plugin actually invokes from the plugin's
#: own code and requires this list to cover it, so "explicit" does not mean
#: "maintained by memory".
BUNDLED = (
    "budget.py",
    "framework_only.py",
    "interpolation_lint.py",
    "mcp_server.py",
    "obsgate.py",
    "rounds.py",
    "swallow_lint.py",
    "verify_guard.py",
)

PLUGIN_ROOT = Path(__file__).resolve().parent
SOURCE = PLUGIN_ROOT.parent / "python" / "sutradhar_guards"
BUNDLE = PLUGIN_ROOT / "guards"


def differences() -> list[str]:
    """Bundled files that are absent or not byte-identical to their source."""
    out: list[str] = []
    for name in BUNDLED:
        src, dst = SOURCE / name, BUNDLE / name
        if not src.is_file():
            out.append(f"{name}: missing from {SOURCE}")
        elif not dst.is_file():
            out.append(f"{name}: missing from {BUNDLE}")
        elif src.read_bytes() != dst.read_bytes():
            out.append(f"{name}: differs from {src}")
    for path in sorted(BUNDLE.glob("*.py")) if BUNDLE.is_dir() else []:
        if path.name not in BUNDLED:
            out.append(f"{path.name}: in the bundle but not in BUNDLED")
    return out


def sync() -> list[str]:
    """Copy every bundled file. Returns the names actually written."""
    BUNDLE.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name in BUNDLED:
        src, dst = SOURCE / name, BUNDLE / name
        if not src.is_file():
            raise SystemExit(f"[sync-guards] no source file {src}")
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)
            written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    for arg in argv:
        # An unrecognised flag is never ignored: `--chek` would otherwise
        # COPY when the caller asked to compare, which is the one direction
        # that cannot be undone by reading the output.
        if arg not in ("--check", "--help", "-h"):
            print(f"[sync-guards] unknown flag: {arg}", file=sys.stderr)
            return 2
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    if "--check" in argv:
        drift = differences()
        if drift:
            print(f"[sync-guards] {len(drift)} bundled guard(s) out of date "
                  f"with {SOURCE}:", file=sys.stderr)
            for line in drift:
                print(f"  {line}", file=sys.stderr)
            print("Run `python3 plugin/sync_guards.py` to refresh them.",
                  file=sys.stderr)
            return 1
        print(f"[sync-guards] OK - {len(BUNDLED)} bundled guard(s) are "
              f"byte-identical to {SOURCE}.")
        return 0

    written = sync()
    if written:
        print(f"[sync-guards] updated {len(written)} file(s): "
              f"{', '.join(written)}")
    else:
        print(f"[sync-guards] nothing to do - {len(BUNDLED)} file(s) already "
              f"match {SOURCE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""sutradhar_guards - mechanical guards for agent-built Python codebases.

Copy-in, stdlib-only. See each module's docstring for the incident that
earned it and the usage pattern.

  budget               design-time cardinalities, enforced by tests (CLI + library)
  rounds               flight recorder: stop rule, residual register, rule attribution
  verify_guard         prove a guard can fail: revert the fix, demand red (CLI + library)
  swallow_lint         silent-exception-swallow ratchet (CLI + library)
  interpolation_lint   query-string injection guard (CLI + library)
  ratchet              shrink-only allowlist library for class-invariant tests
  envgate              env-gated test tiers that audit their own skip gates
  claim_check          ground every number in generated text (AI/LLM surfaces)
  golden               golden-dataset gate with declared tolerance + reasoned re-baseline
  detectors            ready-made ratchet detectors (imports, unbounded ORDER BY)
  obsgate              observability floor as a provenance gate (doctrine 6.6)
  dead_route_lint      tests that cannot fail: weak assertions + dead routes
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
__version__ = "0.3.0"

# Exports are resolved LAZILY (PEP 562). Importing the submodules eagerly
# here made `python -m sutradhar_guards.budget` emit, on every single run:
#
#   RuntimeWarning: 'sutradhar_guards.budget' found in sys.modules after
#   import of package 'sutradhar_guards', but prior to execution of
#   'sutradhar_guards.budget'; this may result in unpredictable behaviour
#
# because `-m` imports the package first, which imported the submodule,
# before runpy executed that submodule as `__main__`. Six of ten tools
# printed that on stderr forever. Noise on a guard's own stderr teaches
# people to stop reading stderr, which is the one habit these tools need.
#
# NOTE: the `budget` CONTEXT MANAGER is deliberately not exported here.
# A package attribute named `budget` shadows the `budget` SUBMODULE, so
# `sutradhar_guards.budget` would mean the function or the module
# depending on import order. Import it from the submodule:
#     from sutradhar_guards.budget import budget
# `test_no_export_shadows_a_submodule` walks every submodule to enforce this.
_EXPORTS = {
    "Ratchet": "ratchet",
    "RatchetError": "ratchet",
    "selfcheck_detector": "ratchet",
    "Budget": "budget",
    "BudgetError": "budget",
    "load_budgets": "budget",
    "Finding": "rounds",
    "Round": "rounds",
    "RoundError": "rounds",
    "load_rounds": "rounds",
    "residual_register": "rounds",
    "stop_rule": "rounds",
    "DECORATION": "verify_guard",
    "INCONCLUSIVE": "verify_guard",
    "VERIFIED": "verify_guard",
    "classify": "verify_guard",
    "verify": "verify_guard",
    "EnvGate": "envgate",
    "apply_env_gates": "envgate",
    "audit_skip_gates": "envgate",
    "extract_numbers": "claim_check",
    "ground_claims": "claim_check",
    "GoldenError": "golden",
    "GoldenGate": "golden",
    "find_order_by_without_limit": "detectors",
    "find_unresolved_relative_imports": "detectors",
    "find_dead_routes": "dead_route_lint",
    "find_unfailable_assertions": "dead_route_lint",
    # obsgate's verdict constants are NOT exported: verify_guard already
    # owns the package-level INCONCLUSIVE, and two constants with one name
    # and different owners is the shadowing class again. Import verdicts
    # from the submodule: from sutradhar_guards.obsgate import WITNESSED
    "parse_metrics": "obsgate",
    "check_floor": "obsgate",
    "FloorResult": "obsgate",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    """Resolve a public name to its submodule on first access (PEP 562)."""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(f".{module}", __name__), name)
    globals()[name] = value  # cache: __getattr__ is only consulted on a miss
    return value


def __dir__() -> list:
    return sorted(set(globals()) | set(_EXPORTS))

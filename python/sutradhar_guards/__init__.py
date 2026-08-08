"""sutradhar_guards - mechanical guards for agent-built Python codebases.

Copy-in, stdlib-only. See each module's docstring for the incident that
earned it and the usage pattern.

  budget               design-time cardinalities, enforced by tests (CLI + library)
  verify_guard         prove a guard can fail: revert the fix, demand red (CLI + library)
  swallow_lint         silent-exception-swallow ratchet (CLI + library)
  interpolation_lint   query-string injection guard (CLI + library)
  ratchet              shrink-only allowlist library for class-invariant tests
  envgate              env-gated test tiers that audit their own skip gates
  claim_check          ground every number in generated text (AI/LLM surfaces)
  golden               golden-dataset gate with declared tolerance + reasoned re-baseline
  detectors            ready-made ratchet detectors (imports, unbounded ORDER BY)
"""

__version__ = "0.3.0.dev0"

from .ratchet import Ratchet, RatchetError, selfcheck_detector  # noqa: F401
# NOTE: the `budget` CONTEXT MANAGER is deliberately not re-exported here.
# A package attribute named `budget` shadows the `budget` SUBMODULE, so
# `sutradhar_guards.budget` would mean the function or the module
# depending on import order. Import it from the submodule:
#     from sutradhar_guards.budget import budget
from .budget import Budget, BudgetError, load_budgets  # noqa: F401
from .verify_guard import (  # noqa: F401
    DECORATION,
    INCONCLUSIVE,
    VERIFIED,
    classify,
    verify,
)
from .envgate import EnvGate, apply_env_gates, audit_skip_gates  # noqa: F401
from .claim_check import extract_numbers, ground_claims  # noqa: F401
from .golden import GoldenError, GoldenGate  # noqa: F401
from .detectors import (  # noqa: F401
    find_order_by_without_limit,
    find_unresolved_relative_imports,
)

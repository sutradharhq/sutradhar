"""sutradhar_guards - mechanical guards for agent-built Python codebases.

Copy-in, stdlib-only. See each module's docstring for the incident that
earned it and the usage pattern.

  swallow_lint         silent-exception-swallow ratchet (CLI + library)
  interpolation_lint   query-string injection guard (CLI + library)
  ratchet              shrink-only allowlist library for class-invariant tests
  envgate              env-gated test tiers that audit their own skip gates
  claim_check          ground every number in generated text (AI/LLM surfaces)
  golden               golden-dataset gate with declared tolerance + reasoned re-baseline
  detectors            ready-made ratchet detectors (imports, unbounded ORDER BY)
"""

__version__ = "0.2.0"

from .ratchet import Ratchet, RatchetError, selfcheck_detector  # noqa: F401
from .envgate import EnvGate, apply_env_gates, audit_skip_gates  # noqa: F401
from .claim_check import extract_numbers, ground_claims  # noqa: F401
from .golden import GoldenError, GoldenGate  # noqa: F401
from .detectors import (  # noqa: F401
    find_order_by_without_limit,
    find_unresolved_relative_imports,
)

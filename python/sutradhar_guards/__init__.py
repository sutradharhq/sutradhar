"""sutradhar_guards - mechanical guards for agent-built Python codebases.

Copy-in, stdlib-only. See each module's docstring for the incident that
earned it and the usage pattern.

  swallow_lint         silent-exception-swallow ratchet (CLI + library)
  interpolation_lint   query-string injection guard (CLI + library)
  ratchet              shrink-only allowlist library for class-invariant tests
  envgate              env-gated test tiers that audit their own skip gates
"""

from .ratchet import Ratchet, RatchetError, selfcheck_detector  # noqa: F401
from .envgate import EnvGate, apply_env_gates, audit_skip_gates  # noqa: F401

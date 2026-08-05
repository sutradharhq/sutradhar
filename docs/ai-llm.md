# AI/LLM playbook

For products that ship model-backed features. The one-line rule: **the
model phrases; it never invents.** Everything below is machinery for
holding that line mechanically instead of by prompt hope.

## Grounding and the claim check

Every number in generated output is traceable to a computed value or
flagged as unverifiable - checked by code, after generation, every time.
`sutradhar_guards.claim_check` is the shipped net:

```python
from sutradhar_guards.claim_check import ground_claims

witnessed = [{"value": v, "unit": u} for v, u in computed_values]
flags = ground_claims(generated_text, witnessed, rel_tol=0.005)
response["unverifiable_claims"] = flags   # surface them; never strip them
```

Hard-won details encoded in it:

- **An empty witness set flags everything.** If the grounding layer failed
  to fetch values, the honest output is "every number is unverifiable",
  not a clean pass. Degrade direction matters.
- **Units gate matching.** Magnitude-only comparison let "12.4 MW" ground
  against a witnessed 12.4% on our record. Same-unit only; add your
  domain's conversions deliberately or not at all.
- **Dedupe against the model's own admissions**: if the response already
  self-declares a claim as unverifiable, do not double-flag it.

## Structured output is untrusted input

Schema-validate every structured model response, with bounded corrective
retries (send the validation error back once or twice, then degrade
honestly). Never `json.loads` and hope. One shared helper per codebase, so
the retry-and-validate logic exists exactly once.

## Eval sets are golden files for prompts

Every LLM surface gets a small frozen eval (20 to 40 items: intent labels,
extraction fields, refusal cases) run as a regression gate.
`sutradhar_guards.golden.GoldenGate` works for this: freeze the expected
outputs, declare the tolerance (exact-match fields get 0), and a model or
prompt swap must pass parity before it ships. Re-baseline with a reason,
in the same commit as the intentional change.

## Review and replay

- **Human review is non-overridable for consequential artifacts** (letters,
  filings, spend recommendations). Freeze it in the type:
  `requires_review: Literal[True]` - not a boolean someone can flip, not a
  config flag. No surface may render such an artifact as "final".
- **Anchor for replay**: hash the inputs (prompt version, grounded values,
  config) into the artifact so it can be re-derived and disputed later. A
  generated document you cannot reproduce is a liability with letterhead.
- Silent fallbacks between models are provenance violations: if a smaller
  or different model answered, the response says which.

## Budgets

Token spend is metered per surface (and per tenant, if multi-tenant) with
caps that refuse, honestly, when exhausted. A usage-priced dependency
without a budget is an unbounded liability; "the demo never hit it" is the
scale fallacy applied to money.

## Refusal is a feature

A grounded system that cannot support an answer says so, with hints toward
what it CAN answer - a clean refusal with adjacent suggestions beats a
fluent hallucination in every product that matters. Test the refusal paths
in the eval set with the same seriousness as the success paths.

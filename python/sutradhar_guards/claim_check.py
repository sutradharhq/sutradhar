"""Claim check - mechanically ground every number in generated text.

The rule this enforces (doctrine 4.1): a model phrases, it never invents.
Every number in LLM-generated output must be traceable to a computed,
witnessed value - MECHANICALLY, not by prompt hope. The incident that
earned it: a generated regulator-facing document carried figures the
grounding layer had never computed, and a later revision grounded a
current-year claim against last year's value because nothing compared
units or vintages.

Usage:

    from sutradhar_guards.claim_check import ground_claims

    witnessed = [
        {"value": 84.5, "unit": "%"},
        {"value": 1_240_000, "unit": "kWh"},
        {"value": 350_000, "unit": "INR"},
    ]
    ungrounded = ground_claims(generated_markdown, witnessed, rel_tol=0.005)
    if ungrounded:
        response["unverifiable_claims"] = ungrounded   # surface, don't hide

Unit handling, stated honestly: a claim with a unit only grounds against a
witnessed value with the SAME unit (after shorthand expansion: k/M/B,
lakh/crore); a unit-less claim grounds against any value. Cross-unit
conversion (kWh vs MWh) is deliberately out of scope here - add your
domain's conversions before trusting cross-unit grounding, because
magnitude-only comparison let "12.4 MW" ground against a witnessed 12.4%
in the incident above.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import re
from typing import Iterable, Mapping

# number with optional currency prefix, western/Indian digit grouping,
# decimal part, magnitude shorthand, and a trailing unit token.
_NUM_RE = re.compile(
    r"(?P<currency>[₹$€£])?\s?"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<mag>lakh|crore|[LKMB]|Cr)?"
    r"\s?(?P<unit>%|[A-Za-z]{1,8})?",
)

_MAGNITUDE = {
    "K": 1e3, "M": 1e6, "B": 1e9,
    "L": 1e5, "lakh": 1e5, "Cr": 1e7, "crore": 1e7,
}

_CURRENCY_UNIT = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}

# Words that follow a number without being units.
_NOT_UNITS = {
    "of", "to", "in", "and", "or", "the", "per", "for", "on", "at", "by",
    "is", "was", "a", "an", "with", "from",
}


def extract_numbers(text: str) -> list[dict]:
    """Return [{value, unit, raw}] for every quantity in the text."""
    out: list[dict] = []
    for m in _NUM_RE.finditer(text):
        raw_num = m.group("num")
        value = float(raw_num.replace(",", ""))
        mag = m.group("mag")
        if mag:
            value *= _MAGNITUDE[mag]
        unit = m.group("unit") or ""
        if unit.lower() in _NOT_UNITS:
            unit = ""
        if m.group("currency"):
            unit = _CURRENCY_UNIT[m.group("currency")]
        # A bare year ("in 2026") is prose, not a claim. Checked AFTER unit
        # normalization so a stopword following the year does not read as a
        # unit ("2026 the") - the bug the first draft shipped.
        if re.fullmatch(r"(19|20)\d{2}", raw_num) and not (
            m.group("currency") or mag or unit
        ):
            continue
        if not (m.group("currency") or mag or unit):
            # A bare small integer with no unit is usually prose ("3 of the
            # feeders"); still check it, but callers can filter by `bare`.
            out.append({"value": value, "unit": "", "raw": m.group(0).strip(), "bare": True})
        else:
            out.append({"value": value, "unit": unit, "raw": m.group(0).strip(), "bare": False})
    return out


def _matches(claim: dict, w_value: float, w_unit: str, rel_tol: float) -> bool:
    if claim["unit"] and w_unit and claim["unit"].lower() != w_unit.lower():
        return False  # same-unit only; see the module docstring
    if w_value == 0:
        return abs(claim["value"]) < 1e-9
    return abs(claim["value"] - w_value) / abs(w_value) <= rel_tol


def ground_claims(
    text: str,
    witnessed: Iterable[Mapping],
    rel_tol: float = 0.005,
    include_bare: bool = False,
) -> list[dict]:
    """Return the claims in ``text`` NOT traceable to any witnessed value.

    ``witnessed`` is an iterable of {"value": float, "unit": str} (unit may
    be ""). If it is EMPTY, every extracted claim is returned - an empty
    grounding set must flag everything, never pass everything (that
    degrade direction is the whole point).
    """
    wit = [(float(w["value"]), str(w.get("unit", ""))) for w in witnessed]
    ungrounded = []
    for claim in extract_numbers(text):
        if claim["bare"] and not include_bare:
            continue
        if not any(_matches(claim, wv, wu, rel_tol) for wv, wu in wit):
            ungrounded.append(
                {**claim, "reason": "number not traceable to a witnessed value"}
            )
    return ungrounded


# ── selfcheck ───────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    wit = [{"value": 84.5, "unit": "%"}]
    bad = ground_claims("Losses improved to 84.5% and revenue rose ₹2.1Cr.", wit)
    good = ground_claims("Losses improved to 84.5%.", wit)
    empty = ground_claims("Revenue was ₹5L.", [])
    ok = len(bad) == 1 and good == [] and len(empty) == 1
    if not ok:
        print(f"[claim-check] SELFCHECK FAILED: bad={bad} good={good} empty={empty}")
    return ok

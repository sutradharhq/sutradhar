"""The customer-facing summary, phrased by a model.

Doctrine 4.1: the model phrases, it never invents. This one invents.
"""


def summarise(usage_kwh, change_pct):
    """Pretend this came back from an LLM given `usage_kwh` and `change_pct`."""
    # PLANTED DEFECT 4: neither number below is the number that was passed
    # in. The prose is fluent, confident, and wrong - which is exactly why
    # this class needs a mechanical check rather than a careful reader.
    return (
        "Your usage rose 47% this month to 1,240 kWh, "
        "putting you in the top 10% of similar homes."
    )

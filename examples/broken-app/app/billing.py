"""Billing arithmetic. The bulk discount below is the 'fix' whose guard
turns out to be decoration - see tests/test_billing.py."""


def total(units, rate):
    subtotal = units * rate
    if units >= 1000:
        subtotal *= 0.9          # the bulk discount
    return subtotal

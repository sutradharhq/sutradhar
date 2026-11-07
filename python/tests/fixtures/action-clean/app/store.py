# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""The known-clean half of the Action's pair (6.7).

`examples/broken-app` is the tree the Action must fail on; this is the tree
it must pass, with the same shapes written the honest way: the failure is
logged and carried back as a flag the caller must read, and the query is
parameterised instead of interpolated. If the Action went red here, its red
on the broken app would prove nothing.
"""
import logging

log = logging.getLogger(__name__)


def load_items(conn, owner_id):
    """(rows, ok). An empty list with ok=False is a failed read, not "none"."""
    try:
        cur = conn.execute(
            "SELECT id, name FROM items WHERE owner = ?", (owner_id,)
        )
        return cur.fetchall(), True
    except Exception as exc:
        log.warning("load_items failed for %s: %s", owner_id, exc)
        return [], False

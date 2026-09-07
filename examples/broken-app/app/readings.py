"""Device readings. Three planted defects live in this file."""


class Store:
    """Stands in for a database. Raises when the backend is unhappy."""

    def __init__(self, rows=None, healthy=True):
        self.rows = rows or {}
        self.healthy = healthy

    def fetch(self, device_id):
        if not self.healthy:
            raise ConnectionError("readings backend unreachable")
        return self.rows.get(device_id, {})


# PLANTED DEFECT 1 (doctrine 2.7): the outage becomes "no readings".
# Callers cannot tell "this device genuinely reported nothing" from "we
# could not reach the store", and downstream code bills on the difference.
def latest_readings(store, device_id):
    try:
        return store.fetch(device_id)
    except Exception:
        return {}


# PLANTED DEFECT 2 (doctrine 2.6): ORDER BY over a table that grows with
# every reading, with no LIMIT. Fine on the demo dataset, a memory bomb on
# a device that has been reporting for a year.
HISTORY_QUERY = "SELECT ts, units FROM readings WHERE device = ? ORDER BY ts DESC"


# PLANTED DEFECT 3 (doctrine 2.8): the device id is interpolated into SQL.
# Today's caller passes an int, so it is "safe" - right up until someone
# parameterises it from a request.
def readings_for(device_id):
    return f"SELECT ts, units FROM readings WHERE device = '{device_id}'"

def read_or_nothing(s):
    try:
        return s.read()
    except Exception:
        pass

def select_dispatches(ctxs: list, prefixes: list | None) -> list:
    """The dispatches whose uuids start with one of ``prefixes``; all of
    them if there are none. Raises LookupError for a prefix that matches no
    dispatch, or more than one."""
    if not prefixes:
        return list(ctxs)
    chosen = []
    for prefix in prefixes:
        found = [c for c in ctxs if c.dispatch_uuid.startswith(prefix)]
        if len(found) != 1:
            raise LookupError(f"{prefix!r} matches {len(found)} dispatches")
        chosen += [c for c in found if c not in chosen]
    return chosen

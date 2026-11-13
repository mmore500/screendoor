from ..auxlib._DispatchContext import DispatchContext


def select_dispatches(
    ctxs: list[DispatchContext], prefixes: list[str] | None
) -> list[DispatchContext]:
    """Select the dispatches whose uuids start with one of `prefixes`, or
    all of them if there are no prefixes.

    Parameters
    ----------
    ctxs : list of DispatchContext
        The dispatches to choose from.
    prefixes : list of str or None
        Prefixes of `dispatch_uuid`s.

    Returns
    -------
    list of DispatchContext
        The chosen dispatches, in prefix order, each once.

    Raises
    ------
    LookupError
        If a prefix matches no dispatch, or more than one.
    """
    if not prefixes:
        return list(ctxs)
    chosen = []
    for prefix in prefixes:
        found = [c for c in ctxs if c.dispatch_uuid.startswith(prefix)]
        if len(found) != 1:
            raise LookupError(f"{prefix!r} matches {len(found)} dispatches")
        chosen += [c for c in found if c not in chosen]
    return chosen

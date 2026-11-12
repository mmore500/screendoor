from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ..auxlib._DispatchContext import DispatchContext


def select_dispatches(
    ctxs: list[DispatchContext], prefixes: list[str] | None
) -> list[DispatchContext]:
    """The dispatches whose uuids start with one of ``prefixes``; all of
    them if there are none. Raises LookupError for a prefix that matches no
    dispatch, or more than one.

    Parameters
    ----------
    ctxs : list of DispatchContext
        The dispatches to choose from.
    prefixes : list of str or None
        Prefixes of dispatch_uuids.

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

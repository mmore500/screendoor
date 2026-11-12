from ._validate import make_action


def succeed(summary: dict) -> dict:
    """Close the dispatch as succeeded.

    Parameters
    ----------
    summary : dict
        The dispatch's result, JSON-serializable.

    Returns
    -------
    dict
        The ``succeed`` action.

    Raises
    ------
    TypeError
        If ``summary`` is not a dict.
    ValueError
        If ``summary`` is not JSON-serializable.
    """
    if not isinstance(summary, dict):
        raise TypeError("succeed summary must be a dict")
    return make_action("succeed", summary=summary)

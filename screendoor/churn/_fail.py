from ._validate import make_action


def fail(reason: str) -> dict:
    """Close the dispatch as failed.

    Parameters
    ----------
    reason : str
        Why it failed.

    Returns
    -------
    dict
        The ``fail`` action.
    """
    return make_action("fail", reason=str(reason))

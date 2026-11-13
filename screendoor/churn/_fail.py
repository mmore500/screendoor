from ._validate import make_action


def fail(reason: str) -> dict:
    """Create a `fail` action, completing the dispatch as failed.

    Parameters
    ----------
    reason : str
        Why the dispatch failed.

    Returns
    -------
    dict
        The action.
    """
    return make_action("fail", reason=str(reason))

from ._validate import make_action


def memo(data: dict) -> dict:
    """Create a `memo` action, recording assay-private state.

    After a memo, the daemon calls churn again in the same tick, with the
    new state appended to `memo`.

    Parameters
    ----------
    data : dict
        The state, JSON-serializable.

    Returns
    -------
    dict
        The action.

    Raises
    ------
    TypeError
        If `data` is not a dict.
    ValueError
        If `data` is not JSON-serializable.
    """
    if not isinstance(data, dict):
        raise TypeError("memo data must be a dict")
    return make_action("memo", data=data)

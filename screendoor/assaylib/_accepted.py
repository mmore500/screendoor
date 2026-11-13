import typing


def accepted(result: typing.Any) -> bool:
    """Does a trial result say yes, as `true` or `{"accept": true}`?

    The built-in assays read pass/fail results this way.

    Parameters
    ----------
    result : Any
        A trial's result.

    Returns
    -------
    bool
        True if the result accepts.
    """
    if isinstance(result, dict):
        return bool(result.get("accept"))
    return result is True

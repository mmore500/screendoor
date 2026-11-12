import typing

from ..auxlib._canonical_json import canonical_json


def check_json(value: typing.Any, what: str) -> None:
    """Check that ``value`` is JSON-serializable.

    Parameters
    ----------
    value : Any
        The value to check.
    what : str
        What it is, for the error message.

    Raises
    ------
    ValueError
        If ``value`` is not JSON-serializable.
    """
    try:
        canonical_json(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{what} must be JSON-serializable: {e}") from None


def make_action(name: str, **kwargs: typing.Any) -> dict:
    """An action for churn to return: ``{"action": name, "kwargs": kwargs}``.

    Parameters
    ----------
    name : str
        A name in ORDER.
    **kwargs
        The action's arguments, JSON-serializable.

    Returns
    -------
    dict
        The action.

    Raises
    ------
    ValueError
        If ``kwargs`` is not JSON-serializable.
    """
    check_json(kwargs, f"{name} kwargs")
    return {"action": name, "kwargs": kwargs}

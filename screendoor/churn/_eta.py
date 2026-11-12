import datetime

from ._validate import make_action


def eta(eta: str | datetime.datetime) -> dict:
    """Report the estimated completion time, as an ISO timestamp.

    Parameters
    ----------
    eta : str or datetime.datetime
        The time, or an ISO-8601 timestamp of it.

    Returns
    -------
    dict
        The ``eta`` action.

    Raises
    ------
    ValueError
        If ``eta`` is a string but not ISO-8601.
    """
    if isinstance(eta, datetime.datetime):
        eta = eta.isoformat()
    datetime.datetime.fromisoformat(eta)  # raises unless ISO
    return make_action("eta", eta=eta)

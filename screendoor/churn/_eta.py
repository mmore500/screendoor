import datetime

from ._validate import make_action


def eta(eta: str | datetime.datetime) -> dict:
    """Create an `eta` action, reporting the dispatch's estimated completion
    time.

    Parameters
    ----------
    eta : str or datetime.datetime
        The time, or an ISO-8601 timestamp of it.

    Returns
    -------
    dict
        The action, with `eta` as an ISO-8601 timestamp.

    Raises
    ------
    ValueError
        If `eta` is a string that is not ISO-8601.
    """
    if isinstance(eta, datetime.datetime):
        eta = eta.isoformat()
    datetime.datetime.fromisoformat(eta)  # raises unless ISO
    return make_action("eta", eta=eta)

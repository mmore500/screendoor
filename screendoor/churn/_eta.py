import datetime

from ._validate import make_action


def eta(eta: str | datetime.datetime) -> dict:
    """Report the estimated completion time, as an ISO timestamp."""
    if isinstance(eta, datetime.datetime):
        eta = eta.isoformat()
    datetime.datetime.fromisoformat(eta)  # raises unless ISO
    return make_action("eta", eta=eta)

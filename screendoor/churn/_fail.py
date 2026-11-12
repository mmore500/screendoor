from ._validate import make_action


def fail(reason: str) -> dict:
    """Close the dispatch as failed."""
    return make_action("fail", reason=str(reason))

from ._validate import make_action


def succeed(summary: dict) -> dict:
    """Close the dispatch as succeeded."""
    if not isinstance(summary, dict):
        raise TypeError("succeed summary must be a dict")
    return make_action("succeed", summary=summary)

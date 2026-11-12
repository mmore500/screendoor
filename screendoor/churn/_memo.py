from ._validate import make_action


def memo(data: dict) -> dict:
    """Append assay-private state; churn runs again in the same tick."""
    if not isinstance(data, dict):
        raise TypeError("memo data must be a dict")
    return make_action("memo", data=data)

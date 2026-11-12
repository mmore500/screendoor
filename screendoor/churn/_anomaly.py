from ._validate import make_action


def anomaly(message: str, data: dict | None = None) -> dict:
    """Report something surprising but not broken."""
    return make_action("anomaly", message=str(message), data=data or {})

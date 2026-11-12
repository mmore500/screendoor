from ..auxlib._canonical_json import canonical_json


def check_json(value, what: str) -> None:
    try:
        canonical_json(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{what} must be JSON-serializable: {e}") from None


def make_action(name: str, **kwargs) -> dict:
    check_json(kwargs, f"{name} kwargs")
    return {"action": name, "kwargs": kwargs}

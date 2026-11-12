import uuid

_REGISTRY: dict = {}


def register_hook(obj) -> str:
    """Return a hook expression that evaluates to ``obj`` in this process."""
    token = uuid.uuid4().hex
    _REGISTRY[token] = obj
    return f"scd.testing.registered_hook({token!r})"


def registered_hook(token: str):
    return _REGISTRY[token]

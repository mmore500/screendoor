import typing
import uuid

_REGISTRY: dict = {}


def register_hook(obj: typing.Any) -> str:
    """Return a hook expression that evaluates to ``obj`` in this process.

    Parameters
    ----------
    obj : Any
        The object to register.

    Returns
    -------
    str
        A ``scd.testing.registered_hook(...)`` expression.
    """
    token = uuid.uuid4().hex
    _REGISTRY[token] = obj
    return f"scd.testing.registered_hook({token!r})"


def registered_hook(token: str) -> typing.Any:
    """The object ``register_hook`` registered under ``token``.

    Parameters
    ----------
    token : str
        The token in the expression ``register_hook`` returned.

    Returns
    -------
    Any
        The registered object.
    """
    return _REGISTRY[token]

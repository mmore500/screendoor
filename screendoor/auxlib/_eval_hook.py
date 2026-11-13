import typing

DEFAULT_EVAL_CONTEXT = (
    "import importlib; import logging; import screendoor as scd"
)


def make_eval_namespace(eval_context: str | None) -> dict:
    """Execute `eval_context` in a fresh namespace and return it.

    Parameters
    ----------
    eval_context : str or None
        Python statements; None or empty runs `DEFAULT_EVAL_CONTEXT`.

    Returns
    -------
    dict
        The namespace.
    """
    namespace: dict = {}
    exec(eval_context or DEFAULT_EVAL_CONTEXT, namespace)  # noqa: S102
    return namespace


def eval_hook(expression: str, namespace: dict) -> typing.Any:
    """Evaluate a hook or assay expression in `namespace`.

    Parameters
    ----------
    expression : str
        A Python expression.
    namespace : dict
        The globals to evaluate it in, as from `make_eval_namespace`.

    Returns
    -------
    Any
        The expression's value.

    Raises
    ------
    TypeError
        If `expression` is not a string.
    """
    if not isinstance(expression, str):
        raise TypeError(f"hook expression must be a string: {expression!r}")
    return eval(expression, namespace)  # noqa: S307

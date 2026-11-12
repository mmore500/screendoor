DEFAULT_EVAL_CONTEXT = (
    "import importlib; import logging; import screendoor as scd"
)


def make_eval_namespace(eval_context: str | None) -> dict:
    """Exec ``eval_context`` into a fresh namespace."""
    namespace: dict = {}
    exec(eval_context or DEFAULT_EVAL_CONTEXT, namespace)  # noqa: S102
    return namespace


def eval_hook(expression: str, namespace: dict):
    """Evaluate one hook (or assay) expression in ``namespace``."""
    if not isinstance(expression, str):
        raise TypeError(f"hook expression must be a string: {expression!r}")
    return eval(expression, namespace)  # noqa: S307

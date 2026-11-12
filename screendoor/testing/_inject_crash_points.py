import contextlib
import typing

from ..auxlib import _append_jsonl_line


class InjectedCrash(BaseException):
    """Simulated process death; a BaseException, so nothing catches it."""


@contextlib.contextmanager
def inject_crash_points(after_n_appends: int) -> typing.Iterator[None]:
    """Raise InjectedCrash right after the n-th record append in the block.

    Parameters
    ----------
    after_n_appends : int
        The append to crash after, counting from 1.

    Raises
    ------
    InjectedCrash
        Right after the ``after_n_appends``-th append.
    """
    appends = 0

    def hook(path: str, record: dict) -> None:
        nonlocal appends
        appends += 1
        if appends == after_n_appends:
            raise InjectedCrash(f"after {record['event']} -> {path}")

    _append_jsonl_line._after_append_hooks.append(hook)
    try:
        yield
    finally:
        _append_jsonl_line._after_append_hooks.remove(hook)

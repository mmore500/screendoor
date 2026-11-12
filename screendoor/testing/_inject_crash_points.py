import contextlib

from ..auxlib import _append_jsonl_line


class InjectedCrash(BaseException):
    """Simulated process death; a BaseException, so nothing catches it."""


@contextlib.contextmanager
def inject_crash_points(after_n_appends: int):
    """Raise InjectedCrash right after the n-th record append in the block."""
    appends = 0

    def hook(path, record):
        nonlocal appends
        appends += 1
        if appends == after_n_appends:
            raise InjectedCrash(f"after {record['event']} -> {path}")

    _append_jsonl_line._after_append_hooks.append(hook)
    try:
        yield
    finally:
        _append_jsonl_line._after_append_hooks.remove(hook)

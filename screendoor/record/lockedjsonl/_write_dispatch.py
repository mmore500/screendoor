import os

from ._files import DISPATCH_FILE, append


def write_dispatch(*, timeout: float | None = None):
    """Append one event to a workdir's screendoor-dispatch.jsonl, under an
    exclusive lock."""

    def write_dispatch(workdir: str, record: dict) -> dict:
        return append(os.path.join(workdir, DISPATCH_FILE), record, timeout)

    return write_dispatch

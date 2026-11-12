import os

from ._files import DISPATCH_FILE, read_events


def read_dispatch(*, timeout: float | None = None):
    """Read every event in a workdir's screendoor-dispatch.jsonl, under a
    shared lock."""

    def read_dispatch(workdir: str) -> list:
        return read_events(os.path.join(workdir, DISPATCH_FILE), timeout)

    return read_dispatch

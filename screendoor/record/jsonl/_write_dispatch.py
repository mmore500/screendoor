import os

from ._files import DISPATCH_FILE, append


def write_dispatch():
    """Append one event to a workdir's screendoor-dispatch.jsonl."""

    def write_dispatch(workdir: str, record: dict) -> dict:
        return append(os.path.join(workdir, DISPATCH_FILE), record)

    return write_dispatch

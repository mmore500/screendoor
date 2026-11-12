import os

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import DISPATCH_FILE


def read_dispatch():
    """Read every event in a workdir's screendoor-dispatch.jsonl."""

    def read_dispatch(workdir: str) -> list:
        return read_jsonl_tolerant(os.path.join(workdir, DISPATCH_FILE))

    return read_dispatch

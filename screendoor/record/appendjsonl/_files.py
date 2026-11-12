from __future__ import annotations

import os

from ...auxlib._append_jsonl_line import append_jsonl_line

append = append_jsonl_line  # (path, record): stamp and append one record

# a dispatchdir's dispatch records: what was submitted, how it ended, and
# what happened along the way
DISPATCH_SUBMISSIONS_FILE = "dispatch_submissions.jsonl"
DISPATCH_PAYLOADS_FILE = "dispatch_payloads.jsonl"  # `completed` only
DISPATCH_TELEMETRY_FILE = "dispatch_telemetry.jsonl"


def path(ctx: dict, name: str) -> str:
    """The path of one of the dispatch's JSONL files.

    Parameters
    ----------
    ctx : dict
        The dispatch.
    name : str
        The file's name, without ``.jsonl``.

    Returns
    -------
    str
        ``<run dir>/<name>.jsonl``.
    """
    return os.path.join(ctx["run_dir"], f"{name}.jsonl")

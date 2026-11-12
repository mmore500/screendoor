import os

from ...auxlib._append_jsonl_line import append_jsonl_line

DISPATCH_FILE = "screendoor-dispatch.jsonl"


def path(ctx, name: str) -> str:
    return os.path.join(ctx.run_dir, f"{name}.jsonl")


def append(path: str, record: dict) -> dict:
    """Append ``record`` (a dict with "event"), stamping schema and ts."""
    fields = {
        k: v for k, v in record.items() if k not in ("schema", "ts", "event")
    }
    return append_jsonl_line(path, record["event"], **fields)

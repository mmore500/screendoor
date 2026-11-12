import os

from ...auxlib._append_jsonl_line import append_jsonl_line

# a workdir's dispatch records: what was submitted, how it ended, and
# what happened along the way
DISPATCH_SUBMISSIONS_FILE = "dispatch_submissions.jsonl"
DISPATCH_PAYLOADS_FILE = "dispatch_payloads.jsonl"  # `completed` only
DISPATCH_TELEMETRY_FILE = "dispatch_telemetry.jsonl"


def path(ctx, name: str) -> str:
    return os.path.join(ctx.run_dir, f"{name}.jsonl")


def append(path: str, record: dict) -> dict:
    """Append ``record`` (a dict with "event"), stamping schema and ts."""
    fields = {
        k: v for k, v in record.items() if k not in ("schema", "ts", "event")
    }
    return append_jsonl_line(path, record["event"], **fields)

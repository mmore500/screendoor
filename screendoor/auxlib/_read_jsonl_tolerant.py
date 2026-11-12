import json
import logging
import os

from ._append_jsonl_line import SCHEMA


class SchemaTooNewError(RuntimeError):
    """A record's schema is newer than this code understands."""


def read_jsonl_tolerant(path: str) -> list[dict]:
    """Read records, skipping torn or spliced lines with a warning.

    Parameters
    ----------
    path : str
        The JSONL file; a missing one reads as empty.

    Returns
    -------
    list of dict
        The records, in file order.

    Raises
    ------
    SchemaTooNewError
        On a schema newer than this code understands.
    """
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        return parse_jsonl_tolerant(fh.read(), path)


def parse_jsonl_tolerant(data: bytes, path: str) -> list[dict]:
    """Parse a JSONL file's bytes as read_jsonl_tolerant does; ``path`` is
    for messages only.

    Parameters
    ----------
    data : bytes
        The file's contents.
    path : str
        The file's path.

    Returns
    -------
    list of dict
        The records, in order.

    Raises
    ------
    SchemaTooNewError
        On a schema newer than this code understands.
    """
    lines = data.split(b"\n")
    records = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or "event" not in record:
                raise ValueError("not an event record")
        except ValueError:  # includes UnicodeDecodeError
            logging.warning(
                "screendoor: skipping torn line %s:%d: %.80r",
                path,
                lineno,
                line,
            )
            continue
        if record.get("schema", 1) > SCHEMA:
            raise SchemaTooNewError(
                f"{path}:{lineno} has schema {record['schema']}; "
                f"this screendoor reads up to {SCHEMA}"
            )
        records.append(record)
    return records

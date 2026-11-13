import json
import logging
import os


def parse_jsonl_tolerant(data: bytes, path: str) -> list[dict]:
    """Parse the records in JSONL `data`, skipping lines that are torn,
    spliced or not event records.

    Each skipped line is logged as a warning.

    Parameters
    ----------
    data : bytes
        The file's contents.
    path : str
        The file's path, for log messages.

    Returns
    -------
    list of dict
        The records, in order.
    """
    records = []
    for lineno, line in enumerate(data.split(b"\n"), start=1):
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
        records.append(record)
    return records


def read_jsonl_tolerant(path: str) -> list[dict]:
    """Read the records in the JSONL file `path`, skipping torn lines with
    a warning.

    Parameters
    ----------
    path : str
        The JSONL file; a missing file reads as empty.

    Returns
    -------
    list of dict
        The records, in file order.
    """
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        return parse_jsonl_tolerant(fh.read(), path)

import json

from ._read import read


def convert(
    path: str,
    out: str,
    slot_bytes: int | None = None,
    with_index: bool = False,
) -> None:
    """Write the valid records of the slotted file `path` to `out` as plain
    compact JSONL, in index order.

    Parameters
    ----------
    path : str
        The slotted file.
    out : str
        The JSONL file to write.
    slot_bytes : int or None, default None
        The slot size; None takes the file's own.
    with_index : bool, default False
        Whether to write each line as `{"i": index, "r": record}` rather
        than the bare record.
    """
    records = read(path, None, slot_bytes)
    with open(out, "w", encoding="utf-8") as fh:
        for i in sorted(records):
            obj = {"i": i, "r": records[i]} if with_index else records[i]
            line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            fh.write(line + "\n")

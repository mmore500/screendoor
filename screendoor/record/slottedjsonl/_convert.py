import json

from ._read import read


def convert(
    path: str,
    out: str,
    slot_bytes: int | None = None,
    with_index: bool = False,
) -> None:
    """Write the valid records to ``out`` as plain compact JSONL.

    Records come in index order; with ``with_index``, each line is
    ``{"i": index, "r": record}``.

    Parameters
    ----------
    path : str
        The slotted file.
    out : str
        The JSONL file to write.
    slot_bytes : int or None, default None
        The slot size; None takes the file's own.
    with_index : bool, default False
        Write each record with its index.
    """
    records = read(path, None, slot_bytes)
    with open(out, "w", encoding="utf-8") as fh:
        for i in sorted(records):
            obj = {"i": i, "r": records[i]} if with_index else records[i]
            line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            fh.write(line + "\n")

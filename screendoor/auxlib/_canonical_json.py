import json


def canonical_json(obj: object) -> str:
    """Serialize ``obj`` deterministically: sorted keys, no whitespace."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

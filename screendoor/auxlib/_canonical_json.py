import json


def canonical_json(obj: object) -> str:
    """Serialize ``obj`` deterministically: sorted keys, no whitespace.

    Parameters
    ----------
    obj : object
        A JSON-serializable value.

    Returns
    -------
    str
        The compact JSON text, the same for equal values.

    Raises
    ------
    TypeError
        If ``obj`` holds a value JSON cannot represent.
    ValueError
        If ``obj`` holds NaN or infinity.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

import json


def canonical_json(obj: object) -> str:
    """Serialize `obj` to compact JSON with sorted keys, so that equal
    values always serialize the same.

    Parameters
    ----------
    obj : object
        A JSON-serializable value.

    Returns
    -------
    str
        The JSON text, without whitespace.

    Raises
    ------
    TypeError
        If `obj` holds a value JSON cannot represent.
    ValueError
        If `obj` holds NaN or infinity.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

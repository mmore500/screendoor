def accepted(result) -> bool:
    """Whether a trial result says yes: ``true`` or ``{"accept": true}``.

    The built-in assays read pass/fail results this way.
    """
    if isinstance(result, dict):
        return bool(result.get("accept"))
    return result is True

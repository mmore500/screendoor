import uuid

from ._canonical_json import canonical_json


def make_trial_uuid(dispatch_uuid: str, key: object) -> str:
    """``uuid5(dispatch_uuid, canonical_json(key))``.

    Parameters
    ----------
    dispatch_uuid : str
        The trial's dispatch.
    key : object
        The trial's key, JSON-serializable.

    Returns
    -------
    str
        The trial's uuid, the same for equal keys.
    """
    return str(uuid.uuid5(uuid.UUID(dispatch_uuid), canonical_json(key)))

import uuid

from ._canonical_json import canonical_json


def make_trial_uuid(dispatch_uuid: str, key: object) -> str:
    """Derive a trial's uuid from its dispatch and key, as
    `uuid5(dispatch_uuid, canonical_json(key))`.

    Parameters
    ----------
    dispatch_uuid : str
        The uuid of the trial's dispatch.
    key : object
        The trial's key, JSON-serializable.

    Returns
    -------
    str
        The trial's uuid; equal keys give equal uuids.
    """
    return str(uuid.uuid5(uuid.UUID(dispatch_uuid), canonical_json(key)))

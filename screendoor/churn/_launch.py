from ._validate import check_json, make_action


def launch(trials: list[dict]) -> dict:
    """Create a `launch` action, requesting trials.

    Parameters
    ----------
    trials : list of dict
        The trials to request, each `{"key": ..., "cmd": str, "env": {str:
        str}, "weight": number}`. `key` is any JSON value; `env` is
        optional, and names starting `SCREENDOOR_` are reserved. `weight`
        is optional: how much of a job's `trial_batchsize` the trial takes
        up, 1 if not given.

    Returns
    -------
    dict
        The action.

    Raises
    ------
    TypeError
        If a `cmd`, or an `env` name or value, is not a string, or a
        `weight` is not a number.
    ValueError
        If a trial has unknown fields, a reserved `env` name, a `weight`
        that is not positive, or a key that is not JSON-serializable.
    """
    checked = []
    for t in trials:
        unknown = set(t) - {"key", "cmd", "env", "weight"}
        if unknown:
            raise ValueError(f"unknown trial fields {sorted(unknown)}")
        if not isinstance(t["cmd"], str):
            raise TypeError("trial cmd must be a string")
        env = dict(t.get("env", {}))
        for name, value in env.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError(
                    f"env {name!r} must map a string to a string; "
                    "convert the value with str() or json.dumps()"
                )
            if name.startswith("SCREENDOOR_"):
                raise ValueError(f"env name {name!r} is reserved")
        check_json(t["key"], "trial key")
        trial = {"key": t["key"], "cmd": t["cmd"], "env": env}
        if "weight" in t:
            weight = t["weight"]
            if isinstance(weight, bool) or not isinstance(
                weight, (int, float)
            ):
                raise TypeError("trial weight must be a number")
            if not weight > 0:
                raise ValueError("trial weight must be positive")
            trial["weight"] = weight
        checked.append(trial)
    return make_action("launch", trials=checked)

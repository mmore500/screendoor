import json
import typing

from .... import churn as scd_churn
from ....auxlib import canonical_json
from ..._accepted import accepted


def _env_value(timepoint: typing.Any) -> str:
    return timepoint if isinstance(timepoint, str) else json.dumps(timepoint)


def churn(
    dispatch: dict,
    trial_submissions: list[dict],
    trial_payloads: list[dict],
    memo: list[dict],
) -> list[dict]:
    """Replay evolution from each timepoint in turn; stop at the first
    timepoint from which a replay succeeds.

    ``assay_kwargs``:

    * ``timepoints``: where replays start (generations, checkpoint paths,
      ...), scanned in the order given.
    * ``replicates``: replays per timepoint (default 1).
    * ``cmd`` and ``env``: the replay script, which gets ``$timepoint``
      (as JSON unless it is a string), ``$timepoint_index`` and
      ``$replicate``. It succeeds by sending ``true`` or
      ``{"accept": true, ...}`` as its result; churn raises on a trial
      with no result.

    Succeeds with the first potentiated ``timepoint`` and its ``index``,
    or None for both if no replay from any timepoint succeeded, and a
    ``scanned`` row per timepoint tried.

    Parameters
    ----------
    dispatch : dict
        The dispatch record, with ``assay_kwargs``.
    trial_submissions : list of dict
        The dispatch's trial submissions.
    trial_payloads : list of dict
        The dispatch's trial payloads.
    memo : list of dict
        Unused.

    Returns
    -------
    list of dict
        This step's actions.
    """
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    timepoints = kw["timepoints"]
    replicates = int(kw.get("replicates", 1))
    by_key = {canonical_json(t["key"]): t for t in trials}

    scanned = []
    for index, timepoint in enumerate(timepoints):
        keys = [
            {"timepoint": timepoint, "replicate": r} for r in range(replicates)
        ]
        found = [by_key.get(canonical_json(k)) for k in keys]
        progress = scd_churn.progress(
            index, len(timepoints), f"at {timepoint}"
        )
        missing = [k for k, t in zip(keys, found) if t is None]
        if missing:
            return [
                scd_churn.launch(
                    [
                        {
                            "key": k,
                            "cmd": kw["cmd"],
                            "env": {
                                **kw.get("env", {}),
                                "timepoint": _env_value(timepoint),
                                "timepoint_index": str(index),
                                "replicate": str(k["replicate"]),
                            },
                        }
                        for k in missing
                    ]
                ),
                progress,
            ]
        if any(t["state"] == "pending" for t in found):
            return [progress]

        successes = sum(accepted(scd_churn.trial_result(t)) for t in found)
        scanned.append(
            {
                "timepoint": timepoint,
                "successes": successes,
                "replicates": replicates,
            }
        )
        if successes:
            return [
                scd_churn.succeed(
                    {
                        "timepoint": timepoint,
                        "index": index,
                        "scanned": scanned,
                    }
                )
            ]
    return [
        scd_churn.succeed(
            {"timepoint": None, "index": None, "scanned": scanned}
        )
    ]

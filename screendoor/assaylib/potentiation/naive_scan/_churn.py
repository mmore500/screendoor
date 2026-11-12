import json

from .... import churn as scd_churn
from ....auxlib import canonical_json
from ..._accepted import accepted


def _env_value(timepoint) -> str:
    return timepoint if isinstance(timepoint, str) else json.dumps(timepoint)


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Replay evolution from each timepoint in turn; stop at the first
    timepoint from which a replay succeeds.

    ``assay_kwargs``:

    * ``timepoints``: where replays start (generations, checkpoint paths,
      ...), scanned in the order given.
    * ``replicates``: replays per timepoint (default 1).
    * ``cmd`` and ``env``: the replay script, which gets ``$timepoint``
      (as JSON unless it is a string), ``$timepoint_index`` and
      ``$replicate``. It succeeds by sending ``true`` or
      ``{"accept": true, ...}`` as its result.
    * ``max_failed``: trials that may fail or send no result, in all,
      before the dispatch fails (default 0); they count as no success.

    Succeeds with the first potentiated ``timepoint`` and its ``index``,
    or None for both if no replay from any timepoint succeeded, and a
    ``scanned`` row per timepoint tried.
    """
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    timepoints = kw["timepoints"]
    replicates = int(kw.get("replicates", 1))
    by_key = {canonical_json(t["key"]): t for t in trials}

    scanned, n_failed = [], 0
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

        ok = [
            t["result"]
            for t in found
            if t["status"] == "succeeded" and t["result"] is not None
        ]
        n_failed += len(found) - len(ok)
        if n_failed > kw.get("max_failed", 0):
            return [scd_churn.fail(f"{n_failed} replays failed")]
        successes = sum(map(accepted, ok))
        scanned.append(
            {
                "timepoint": timepoint,
                "successes": successes,
                "replicates": replicates,
                "failed": len(found) - len(ok),
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

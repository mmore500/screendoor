from .... import churn as scd_churn

DEFAULT_CMD = (
    'echo \'!!!screendoor:telemetry {"hello": "world"}\'; '
    "echo '!!!screendoor:payload true'"
)


def churn(
    dispatch: dict,
    trial_submissions: list[dict],
    trial_payloads: list[dict],
    memo: list[dict],
) -> list[dict]:
    """Launch `n` (default 1) copies of `cmd`, each with `$i` and `env`,
    and succeed with what they sent.

    Churn raises if any trial has no result.

    Parameters
    ----------
    dispatch : dict
        The dispatch record, with `assay_kwargs`.
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
    n = kw.get("n", 1)
    if not trials:
        return [
            scd_churn.launch(
                [
                    {
                        "key": {"i": i},
                        "cmd": kw.get("cmd", DEFAULT_CMD),
                        "env": {**kw.get("env", {}), "i": str(i)},
                    }
                    for i in range(n)
                ]
            )
        ]
    done = [t for t in trials if t["state"] == "complete"]
    if len(done) < n:
        return [scd_churn.progress(len(done), n)]
    return [
        scd_churn.succeed(
            {
                "outcomes": [
                    {
                        "i": t["key"]["i"],
                        "result": scd_churn.trial_result(t),
                        "channels": t["channels"],
                    }
                    for t in sorted(trials, key=lambda t: t["key"]["i"])
                ]
            }
        )
    ]

from .... import churn as scd_churn

DEFAULT_CMD = (
    'echo \'!!!screendoor:telemetry {"hello": "world"}\'; '
    "echo '!!!screendoor:payload true'"
)


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Smoke test: launch ``n`` (default 1) copies of ``cmd``, each with
    ``$i`` and ``env``, and succeed with what they sent; raises if any
    trial has no result."""
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

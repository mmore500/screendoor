from .... import churn as scd_churn

DEFAULT_CMD = (
    'echo \'!!!screendoor:telemetry {"hello": "world"}\'; '
    "echo '!!!screendoor:payload true'"
)


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Smoke test: launch n copies of cmd, wait, report what came back."""
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
                        "env": {"i": str(i), **kw.get("env", {})},
                    }
                    for i in range(n)
                ]
            )
        ]
    done = [t for t in trials if t["state"] == "complete"]
    if len(done) < n:
        return [scd_churn.progress(len(done), n)]
    bad = sum(t["status"] != "succeeded" for t in trials)
    if bad:
        return [scd_churn.fail(f"{bad}/{n} trials failed")]
    return [
        scd_churn.succeed(
            {
                "outcomes": [
                    {
                        "i": t["key"]["i"],
                        "result": t["result"],
                        "channels": t["channels"],
                    }
                    for t in sorted(trials, key=lambda t: t["key"]["i"])
                ]
            }
        )
    ]

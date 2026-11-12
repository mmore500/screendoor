from .... import act

DEFAULT_CMD = (
    'echo \'!!!screendoor:telemetry {"hello": "world"}\'; '
    "echo '!!!screendoor:result true'"
)


def churn(dispatch, trials, memo, *, rng):
    """Smoke test: launch n copies of cmd, wait, report what came back."""
    kw = dispatch["assay_kwargs"]
    n = kw.get("n", 1)
    if not trials:
        return [
            act.launch(
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
        return [act.progress(len(done), n)]
    bad = sum(t["status"] != "succeeded" for t in trials)
    if bad:
        return [act.fail(f"{bad}/{n} trials failed")]
    return [
        act.succeed(
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

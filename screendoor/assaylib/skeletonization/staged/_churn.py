import math
import typing

from .... import churn as scd_churn
from ....auxlib._canonical_json import canonical_json
from ....auxlib._encode_sites import encode_sites
from ..._accepted import accepted
from .._knockout._search_churn import _as_dict, _masked_sequence, _trial_env
from ._StagedSearch import StagedSearch

PHASES = {"controls": 0, "rank": 2, "confirm": 3}


def _screens(kw: dict) -> list[dict]:
    """List each screen's own `cmd` and `env`, cheapest first."""
    screens = kw.get("screens", 1)
    return [{}] * screens if isinstance(screens, int) else list(screens)


def _trial(kw: dict, n: int, request: tuple) -> dict:
    """Build the trial that answers a search's request."""
    kind, stage, deleted, *index = request
    retained = frozenset(range(n)) - deleted
    key = {"retained": encode_sites(retained)}
    if kind == "screen":
        screen = _screens(kw)[stage]
        key["screen"] = stage
        env = _trial_env(kw, n, retained, 0)
        env = {**env, **screen.get("env", {}), "screen": str(stage)}
        return {"key": key, "cmd": screen.get("cmd", kw["cmd"]), "env": env}
    key["sample" if stage == "rank" else "replicate"] = index[0]
    if stage in ("confirm", "jackknife"):
        key[stage] = 1  # fresh scores, apart from the ranking's
    env = _trial_env(kw, n, retained, index[0])
    if stage in ("recontrol", "reconfirm"):  # the costlier trial
        again = kw["reconfirm"]
        key["reconfirm"] = 1
        env = {**env, **again.get("env", {}), "reconfirm": "1"}
        return {"key": key, "cmd": again.get("cmd", kw["cmd"]), "env": env}
    return {"key": key, "cmd": kw["cmd"], "env": env}


def _score(
    kw: dict, result: typing.Any, baseline: dict | None
) -> float | None:
    """Read a long trial's score; None if the result is not viable, or
    has a `require_atleast` field below the wildtype's."""
    r = _as_dict(result)
    if "accept" in r:
        raise ValueError("staged needs scores from its long trials")
    if r.get("viable", True) is False:
        return None
    fields = kw.get("require_atleast", ())
    missing = [f for f in ("score", *fields) if f not in r]
    if missing:
        raise ValueError(f"trial result lacks {missing}: {r!r}")
    for field in fields if baseline else ():
        if any(got < want for got, want in zip(r[field], baseline[field])):
            return None
    return float(r["score"])


def _summary(
    kw: dict, search: StagedSearch, result: dict, trials: int, waves: int
) -> dict:
    retained = result["retained"]
    summary = {
        "policy": search.policy,
        "n_sites": len(search.sites),
        "retained": encode_sites(retained),
        "retained_count": len(retained),
        "status": "complete",
        "waves": waves,
        "trials": trials,
        "critical": encode_sites(result["critical"]),
        "redundant_sets": [
            {"screen": tier, "sites": encode_sites(sites)}
            for tier, sites in result["redundant"]
        ],
        "adding_up": [
            {"screen": tier, "sites": encode_sites(sites)}
            for tier, sites in result["adding_up"]
        ],
        "kept": encode_sites(result["kept"]),
        "released": encode_sites(result["released"]),
        "pool_certified": result["certified"],
        "ranking": result["ranking"],
        "effects": result["effects"],
        # infinite if the ranking took no trials: a pool of one site
        "effects_error": (
            result["error"] if math.isfinite(result["error"]) else None
        ),
        "predicted_cutoff": result["predicted_cutoff"],
        "confirmations": result["confirmations"],
        "stats": result["stats"],
        "control": {
            **search.controls.summary(),
            "margin": search.controls.margin,
            "error_rate": search.sequential.error_rate,
            "stage": search.sequential.summary("sprt"),
        },
    }
    if search.reconfirm is not None:
        summary["reconfirm_every"] = result["reconfirm_every"]
        summary["reconfirm_control"] = {
            **search.recontrols.summary(),
            "margin": search.recontrols.margin,
            "stage": search.resequential.summary("sprt"),
        }
    if "sequence" in kw:
        summary["skeleton"] = _masked_sequence(kw, retained)
    return summary


def make_churn(
    *, num_control_trials: int = 40
) -> typing.Callable[[dict, list[dict], list[dict], list[dict]], list[dict]]:
    """Create a churn function that skeletonizes in stages: screens for
    the minimal critical sets, a ranking of the remaining sites by
    regression, and a confirmed cutoff.

    Every tick replays a `StagedSearch` from the start over the recorded
    trials, until it asks for a trial not yet in; churn then launches the
    missing trials and returns. Nothing is memoized. See
    docs/skeletonization.md for the assay kwargs.

    Parameters
    ----------
    num_control_trials : int, default 40
        How many times the wildtype is scored, as the controls every
        knockout's scores are judged against.

    Returns
    -------
    Callable[[dict, list[dict], list[dict], list[dict]], list[dict]]
        The churn function, `churn(dispatch, trial_submissions,
        trial_payloads, memo)`.

    Raises
    ------
    ValueError
        If `num_control_trials` is not positive.
    """
    if int(num_control_trials) < 1:
        raise ValueError("num_control_trials must be positive")

    def churn(
        dispatch: dict,
        trial_submissions: list[dict],
        trial_payloads: list[dict],
        memo: list[dict],
    ) -> list[dict]:
        trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
        kw = dispatch["assay_kwargs"]
        n = len(kw["sequence"]) if "sequence" in kw else int(kw["n_sites"])
        search = StagedSearch(
            n,
            kw,
            seed=kw.get("search_seed", dispatch["meta_seed"]),
            num_control_trials=int(num_control_trials),
        )
        by_key = {canonical_json(t["key"]): t for t in trials}
        run, answers, waves, baseline = search.run(), None, 0, None
        while True:
            try:
                wave = run.send(answers)
            except StopIteration as stop:
                summary = _summary(kw, search, stop.value, len(trials), waves)
                return [scd_churn.succeed(summary)]
            waves += 1
            missing, waiting, answers = {}, 0, []
            for request in wave:
                trial = _trial(kw, n, request)
                found = by_key.get(canonical_json(trial["key"]))
                if found is None:
                    missing[canonical_json(trial["key"])] = trial
                elif found["state"] == "pending":
                    waiting += 1
                elif request[0] == "screen":
                    answers.append(not accepted(scd_churn.trial_result(found)))
                else:
                    result = scd_churn.trial_result(found)
                    answers.append(_score(kw, result, baseline))
                    if request[1] == "control" and baseline is None:
                        baseline = _as_dict(result)
            if missing or waiting:
                stage = PHASES.get(search.phase, 1)  # of 4: the rest screen
                message = (
                    f"{search.policy}: {search.phase}, wave {waves}, "
                    f"{len(search.tally['critical'])} critical, "
                    f"{len(search.tally['kept'])} kept, "
                    f"{waiting + len(missing)} trials outstanding"
                )
                launch = (
                    [scd_churn.launch(list(missing.values()))]
                    if missing
                    else []
                )
                return [*launch, scd_churn.progress(stage, 4, message)]

    return churn


churn = make_churn()

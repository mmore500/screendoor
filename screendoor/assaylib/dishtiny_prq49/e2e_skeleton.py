"""Skeletonize a DISHTINY prq49 genome end to end, as one assay: strip
statically dead code, knock out what leaves competitions bit-identical,
then what costs no fitness. See docs/dishtiny_prq49.md."""

import itertools
import json
from statistics import fmean
import typing

from ... import churn as scd_churn
from ...auxlib._canonical_json import canonical_json
from ...auxlib._decode_sites import decode_sites
from ...auxlib._encode_sites import encode_sites
from ..skeletonization._knockout._controls import beta_quantile
from ..skeletonization.hybrid._churn import make_churn as make_hybrid_churn
from ..skeletonization.staged._churn import make_churn as make_staged_churn
from ._ops import is_nop
from ._units_of import units_of

STAGES = (
    "strip",
    "identity:modules",
    "strip",
    "identity:outputs",
    "strip",
    "identity:calculations",
    "strip",
    "identity:all",
    "strip",
    "fitness:modules",
    "strip",
    "fitness:outputs",
    "strip",
    "fitness:calculations",
    "strip",
    "fitness:all",
    "strip",
    "final",
)
DEFAULTS = {
    "cmd": "python3 -m screendoor.assaylib.dishtiny_prq49.run_trial",
    "env": {},
    "stages": STAGES,
    "knockout": "",  # positions out before the first stage, as `0-5,9`
    "small": [12288, 36],  # updates, cells: 1.5 group lifetimes
    "screen": [8192, 576],  # one lifetime, on a world no control dies out of
    "full": [24576, 1024],  # three group lifetimes
    # the seconds after which rundishtiny ends a competition of each size
    # where it stands (its RUN_SECONDS), and how many later a run still
    # going is killed
    "run_seconds": {"small": 60, "screen": 600, "full": 2400},
    "overhead_seconds": 10,
    "pruner_timeout": 1800,
    # an identity search's tests, rundishtiny's own: the knockout and the
    # wildtype, each alone in a world of each size, side by side until
    # they differ, which most knockouts that show do in a second
    "divergence": [[2048, 100], [8192, 100]],
    # the size of each world an identity audit then competes in, against
    # the wildtype, cheapest first: the same worlds in every audit, each
    # size's at once, and a size only if those before it all pass
    "identity_worlds": [[12288, 36]] * 8 + [[24576, 400]] * 8,
    "identity": {},
    "fitness": {},
    "reconfirm": {},
    "num_control_trials": 400,
    "num_screen_control_trials": 100,
    "num_full_control_trials": 100,
    "screen_error_rate": 0.001,
    "final_replicates": 64,
    "world_seed": 0,
}
IDENTITY = {
    "batch_size": 56,
    "replicates": 1,
    # audits, the costly tests, pace themselves from every fourth commit
    "audit_every": 4,
    "audit_adaptive": True,
    "max_rollbacks": 1000,
}
FITNESS = {
    "screens": 1,
    "batch_size": 40,
    "abs_tol": 0.15,  # of a share of cells
    "jackknife_replicates": 32,
    "max_replicates": 1024,
}
# full-size confirmations, the costly tests, pace themselves from every
# fourth small-size acceptance
RECONFIRM_EVERY = 4
Stage = tuple[list[dict], dict | None]  # actions, and the outcome once done


def lethal_share(controls: list[float], error_rate: float) -> float:
    """Find the share of cells that a wildtype control falls below with
    probability `error_rate`: under it, a knockout is graded lethal.

    A share lies between 0 and 1, and the wildtype against itself is as
    likely to hold `x` of the cells as `1 - x`, so the controls are fit
    by a symmetric beta distribution, from their spread about one half.

    Parameters
    ----------
    controls : list of float
        The wildtype's shares of cells against itself.
    error_rate : float
        The chance that a harmless knockout is graded lethal.

    Returns
    -------
    float
        The threshold; 0 if the controls do not vary, or are all at the
        extremes.
    """
    spread = fmean((x - 0.5) ** 2 for x in controls)
    if not 0.0 < spread < 0.25:
        return 0.0
    shape = (1.0 / (4.0 * spread) - 1.0) / 2.0
    return beta_quantile(error_rate, shape, shape)


def _run_seconds(size: str | list, kw: dict) -> int:
    """Give the seconds a competition may run: of a size named `small`,
    `screen` or `full`, as `run_seconds` has it; of any other, the small
    size's in proportion to updates times cells, and at least 20."""
    if isinstance(size, str):
        return int(kw["run_seconds"][size])
    small = kw["small"]
    scale = size[0] * size[1] / (small[0] * small[1])
    return max(20, round(kw["run_seconds"]["small"] * scale))


def _trial(kw: dict, key: dict, weight: float, **env: typing.Any) -> dict:
    """Build a trial of `run_trial`: the user's `env`, then `DISHTINY_`
    variables named for `env`'s, which win. Its `weight` is the seconds
    it may take, all told."""
    own = {
        f"DISHTINY_{name.upper()}": (
            value if isinstance(value, str) else json.dumps(value)
        )
        for name, value in env.items()
    }
    overhead = {"DISHTINY_OVERHEAD_SECONDS": str(kw["overhead_seconds"])}
    return {
        "key": key,
        "cmd": kw["cmd"],
        "env": {**kw["env"], **overhead, **own},
        "weight": weight,
    }


def _competition(
    kw: dict,
    key: dict,
    size: str,
    knockout: typing.Iterable[int] = (),
    **env: typing.Any,
) -> dict:
    """Build a trial of one competition of the size named, on a world of
    its own: `mode` is `score` unless `env` says otherwise."""
    updates, cells = kw[size]
    return _trial(
        kw,
        key,
        _run_seconds(size, kw) + kw["overhead_seconds"],
        **{
            "mode": "score",
            "knockout": encode_sites(knockout),
            "updates": updates,
            "n_cells": cells,
            "run_seconds": _run_seconds(size, kw),
            **env,
        },
    )


def _result(by_key: dict, trial: dict) -> tuple[str, typing.Any]:
    """Look up a trial's state (`missing`, `pending`, `failed` or `done`)
    and its result."""
    found = by_key.get(canonical_json(trial["key"]))
    if found is None:
        return "missing", None
    if found["state"] == "pending":
        return "pending", None
    if found["result"] is None:
        return "failed", None
    return "done", found["result"]


def _await(by_key: dict, trials: list[dict]) -> tuple[list[dict], list | None]:
    """Collect trials' results: the launch of those missing, and the
    results once all are in (None for a trial that failed)."""
    found = [_result(by_key, t) for t in trials]
    missing = [t for t, (state, _) in zip(trials, found) if state == "missing"]
    launch = [scd_churn.launch(missing)] if missing else []
    if any(state in ("missing", "pending") for state, _ in found):
        return launch, None
    return launch, [result for _, result in found]


def _control(by_key: dict, size: str, replicate: int, count: int) -> dict:
    """Give the key of the trial that is wildtype control `replicate`, of
    `count`, at a size: its own or, where that was inconclusive, the
    trial run in its place, `count` replicates on."""
    while True:
        key = {"control": size, "replicate": replicate}
        result = by_key.get(canonical_json(key), {}).get("result")
        if not (isinstance(result, dict) and "inconclusive" in result):
            return key
        replicate += count


def _strip(kw: dict, name: str, knockout: set, by_key: dict) -> Stage:
    """Run the static pruner on the genome so far, and take its nops."""
    trial = _trial(
        kw,
        {"stage": name},
        kw["pruner_timeout"],
        mode="strip",
        knockout=encode_sites(knockout),
        pruner_timeout=kw["pruner_timeout"],
    )
    actions, results = _await(by_key, [trial])
    if results is None:
        return actions, None
    (result,) = results
    live = {
        p
        for p, o in enumerate(kw["operations"])
        if p not in knockout and not is_nop(o)
    }
    if result is None:
        problem = "the pruner's trial failed"
    elif not set(result["pruned"]) <= live:
        problem = "the pruner changed positions that were not live"
    else:
        return [], {"added": sorted(result["pruned"]), "summary": result}
    warning = scd_churn.warning(
        f"{name}: {problem}; the stage is skipped", dedupe_key=name
    )
    return [warning], {"added": [], "summary": {"skipped": problem}}


def _scoped(
    sub: typing.Callable,
    dispatch: dict,
    kw: dict,
    records: tuple[list[dict], list[dict]],
    inward: typing.Callable[[typing.Any], dict | None],
    wrap: typing.Callable[[dict], dict],
) -> Stage:
    """Run a stage's own churn, `sub`, on the trials that are the stage's.

    `inward` turns a recorded trial's key into the key `sub` knows it by,
    or None for another stage's trial; `wrap` turns a trial `sub` asks for
    into the one to launch, or None to hold it back. Returns `sub`'s
    actions, less `succeed`, and its summary once it succeeds.
    """
    keys = {}
    for e in records[0]:
        inner = inward(e["key"]) if "key" in e else None
        if inner is not None:
            keys[e["trial_uuid"]] = inner
    own = [
        [
            {**e, "key": keys[e["trial_uuid"]]} if "key" in e else e
            for e in part
            if e.get("trial_uuid") in keys
        ]
        for part in records
    ]
    actions, summary = [], None
    for a in sub({**dispatch, "assay_kwargs": kw}, *own, []):
        if a["action"] == "launch":
            trials = list(filter(None, map(wrap, a["kwargs"]["trials"])))
            actions += [scd_churn.launch(trials)] if trials else []
        elif a["action"] == "succeed":
            summary = a["kwargs"]["summary"]
        else:
            actions.append(a)
    return actions, summary


def _positions(units: list, chosen: typing.Iterable[int]) -> set:
    return {p for i in chosen for p in units[i]}


def _identity(
    kw: dict,
    name: str,
    kind: str,
    knockout: set,
    dispatch: dict,
    records: tuple,
) -> Stage:
    """Search, by the `hybrid` policy, for the units whose knockout shows
    nothing: in the search, by rundishtiny's side-by-side test; in its
    audits, also by competitions that must end as the wildtype's own."""
    units, labels = units_of(kind, kw["operations"], frozenset(knockout))
    if not units:
        return [], {"added": [], "summary": {"units": 0}}
    n = len(units)
    # the search's test: two worlds side by side, killed if still
    # running at twice one's time
    first = [[*size, 2 * _run_seconds(size, kw)] for size in kw["divergence"]]
    cheap = sum(kill for _, _, kill in first)
    # an audit's: that test, and a trial for each world, of its
    # competition and the wildtype's own. Each size is a tier
    sizes = kw["identity_worlds"]
    tiers = [len(list(same)) for _, same in itertools.groupby(sizes)]
    tiers[0] += 1

    def wrap(t: dict) -> dict:
        out = decode_sites(t["env"]["knockout"])
        world = t["key"]["replicate"] - 1 if "fresh" in t["key"] else -1
        worlds, weight = [], cheap
        if world >= 0:  # every audit is in the same worlds
            limit = _run_seconds(sizes[world], kw)
            worlds = [[*sizes[world], kw["world_seed"] + world, limit]]
            weight = 2 * (limit + kw["overhead_seconds"])
        return _trial(
            {**kw, "env": t["env"]},
            {"stage": name, "key": t["key"]},
            weight,
            mode="identity",
            knockout=encode_sites(knockout | _positions(units, out)),
            divergence=[] if worlds else first,
            worlds=worlds,
        )

    def inward(key: typing.Any) -> dict | None:
        mine = isinstance(key, dict) and key.get("stage") == name
        return key.get("key") if mine else None

    sub_kw = {
        "search_seed": dispatch["meta_seed"],
        **IDENTITY,
        **kw["identity"],
        "audit_replicates": tiers,
        "n_sites": n,
        "cmd": kw["cmd"],
        "env": kw["env"],
    }
    actions, summary = _scoped(
        make_hybrid_churn(num_control_trials=1),
        dispatch,
        sub_kw,
        records,
        inward,
        wrap,
    )
    if summary is None:
        return actions, None
    deleted = set(range(n)) - decode_sites(summary["retained"])
    return actions, {
        "added": sorted(_positions(units, deleted)),
        "summary": {
            "units": n,
            "deleted_units": [labels[i] for i in sorted(deleted)],
            "retained_units": [
                labels[i] for i in sorted(decode_sites(summary["retained"]))
            ],
            "search": summary,
        },
    }


def _reconfirm_every(done: dict) -> int:
    """Give how many small-size acceptances a fitness stage starts with
    between full-size confirmations: what the fitness stage before left
    it at, each one that passed having doubled it and each that failed
    halved it; for the first such stage, `RECONFIRM_EVERY`."""
    before = [
        outcome["summary"]["search"]["reconfirm_every"]
        for name, outcome in sorted(done.items())
        if name.split(":")[1] == "fitness" and "search" in outcome["summary"]
    ]
    return before[-1] if before else RECONFIRM_EVERY


def _fitness(
    kw: dict,
    name: str,
    kind: str,
    knockout: set,
    dispatch: dict,
    records: tuple,
    by_key: dict,
    done: dict,
) -> Stage:
    """Search, by the `staged` policy, for the units whose knockout costs
    no more than the margin of fitness: a screen for lethal knockouts on
    one world of the screen's size, scores at the small size, and
    confirmations again at the full size, which pace themselves. If the
    search is `two_sided`, the screen also fails a knockout whose share
    is as far over the controls' as a lethal one's is under."""
    units, labels = units_of(kind, kw["operations"], frozenset(knockout))
    if not units:
        return [], {"added": [], "summary": {"units": 0}}
    n = len(units)
    # the screen's threshold: a share few wildtype controls would fall
    # below, on a world of the screen's size
    controls = [
        _competition(kw, {"control": "screen", "replicate": r}, "screen")
        for r in range(kw["num_screen_control_trials"])
    ]
    actions, results = _await(by_key, controls)
    threshold = None
    if results is not None:
        if None in results:
            raise RuntimeError(f"{name}: a screen control failed")
        shares = [float(r["score"]) for r in results]
        threshold = lethal_share(shares, kw["screen_error_rate"])
    everything = encode_sites(range(n))
    two_sided = {**FITNESS, **kw["fitness"]}.get("two_sided", False)
    counts = {
        "small": kw["num_control_trials"],
        "full": kw["num_full_control_trials"],
    }

    def wrap(t: dict) -> dict | None:
        key, out = t["key"], decode_sites(t["env"]["knockout"])
        # with nothing out, the true wildtype: the controls
        positions = knockout | _positions(units, out) if out else set()
        sub = {**kw, "env": t["env"]}
        if "screen" not in key:
            size = "full" if "reconfirm" in key else "small"
            return _competition(sub, outward(key), size, positions)
        if threshold is None:
            return None  # held back until the screen's controls are in
        return _competition(
            sub,
            outward(key),
            "screen",
            positions,
            mode="screen",
            screen_pass=threshold,
            **({"screen_ceiling": 1.0 - threshold} if two_sided else {}),
        )

    def outward(key: dict) -> dict:
        # every stage's controls are the same trials, the wildtype's
        control = key["retained"] == everything and set(key) <= {
            "retained",
            "replicate",
            "reconfirm",
        }
        if control:
            size = "full" if "reconfirm" in key else "small"
            return _control(by_key, size, key["replicate"], counts[size])
        return {"stage": name, "key": key}

    def inward(key: typing.Any) -> dict | None:
        if not isinstance(key, dict):
            return None
        if "control" in key:
            size, count = key["control"], counts.get(key["control"])
            if count is None:
                return None  # the screen's own
            replicate = key["replicate"] % count
            if key != _control(by_key, size, replicate, count):
                return None  # inconclusive: another stands in for it
            inner = {"retained": everything, "replicate": replicate}
            if size == "full":
                inner["reconfirm"] = 1
            return inner
        return key.get("key") if key.get("stage") == name else None

    sub_kw = {
        "search_seed": dispatch["meta_seed"],
        **FITNESS,
        **kw["fitness"],
        "n_sites": n,
        "cmd": kw["cmd"],
        "env": kw["env"],
        "reconfirm": {
            "num_control_trials": kw["num_full_control_trials"],
            "every": _reconfirm_every(done),
            "adaptive": True,
            **kw["reconfirm"],
        },
    }
    more, summary = _scoped(
        make_staged_churn(num_control_trials=kw["num_control_trials"]),
        dispatch,
        sub_kw,
        records,
        inward,
        wrap,
    )
    if summary is None:
        return [*actions, *more], None
    retained = decode_sites(summary["retained"])
    deleted = set(range(n)) - retained
    return [*actions, *more], {
        "added": sorted(_positions(units, deleted)),
        "summary": {
            "units": n,
            "screen_threshold": threshold,
            "deleted_units": [labels[i] for i in sorted(deleted)],
            "retained_units": [labels[i] for i in sorted(retained)],
            "critical_units": [
                labels[i] for i in sorted(decode_sites(summary["critical"]))
            ],
            "kept_units": [
                labels[i] for i in sorted(decode_sites(summary["kept"]))
            ],
            "search": summary,
        },
    }


def _reconfirmed(done: dict) -> list[dict]:
    """List the keys of the full-size competitions already run of the
    genome as the finished stages leave it: those of the reconfirmation
    that accepted the last knockout, if a fitness stage made it."""
    for name, outcome in sorted(done.items(), reverse=True):
        if not outcome["added"]:
            continue  # the genome is as the stage before left it
        search = outcome["summary"].get("search", {})
        deleted = search.get("n_sites", 0) - search.get("retained_count", 0)
        counts = [
            c["reconfirm_replicates"]
            for c in search.get("confirmations", ())
            if c["accepted"] and c["deleted"] == deleted
            if "reconfirm_replicates" in c
        ]
        if name.split(":")[1] != "fitness" or not counts:
            break
        return [
            {
                "stage": name,
                "key": {
                    "retained": search["retained"],
                    "replicate": r,
                    "reconfirm": 1,
                },
            }
            for r in range(counts[-1])
        ]
    return []


def _final(
    kw: dict, name: str, knockout: set, by_key: dict, done: dict
) -> Stage:
    """Score the finished skeleton against the wildtype at the full size,
    beside the wildtype's own full-size controls.

    A competition is not run twice of one genome: where no stage has
    changed the genome since a fitness stage reconfirmed it, that
    reconfirmation's competitions are the first of the skeleton's.
    """
    results = {}
    count = kw["num_full_control_trials"]
    again = _reconfirmed(done)[: kw["final_replicates"]]
    for who, positions, keys in (
        (
            "skeleton",
            knockout,
            again
            + [
                {"stage": name, "replicate": r}
                for r in range(len(again), kw["final_replicates"])
            ],
        ),
        (
            "wildtype",
            set(),
            [_control(by_key, "full", r, count) for r in range(count)],
        ),
    ):
        trials = [_competition(kw, k, "full", positions) for k in keys]
        results[who] = _await(by_key, trials)
    actions = [a for found, _ in results.values() for a in found]
    if any(scores is None for _, scores in results.values()):
        return actions, None
    summary = {}
    for who, (_, found) in results.items():
        scores = [float(r["score"]) for r in found if r is not None]
        mean = sum(scores) / len(scores) if scores else None
        spread = sum((x - mean) ** 2 for x in scores) if scores else 0.0
        summary[who] = {
            "n": len(scores),
            "failed": len(found) - len(scores),
            "mean": mean,
            "sd": (
                (spread / (len(scores) - 1)) ** 0.5
                if len(scores) > 1
                else None
            ),
        }
    summary["skeleton"]["reused"] = len(again)
    return actions, {"added": [], "summary": summary}


def _stage(
    kw: dict,
    name: str,
    spec: str,
    knockout: set,
    dispatch: dict,
    records: tuple,
    by_key: dict,
    done: dict,
) -> Stage:
    step, _, kind = spec.partition(":")
    if step == "strip" and not kind:
        return _strip(kw, name, knockout, by_key)
    if step == "identity":
        return _identity(kw, name, kind, knockout, dispatch, records)
    if step == "fitness":
        return _fitness(
            kw, name, kind, knockout, dispatch, records, by_key, done
        )
    if step == "final" and not kind:
        return _final(kw, name, knockout, by_key, done)
    raise ValueError(f"unknown stage {spec!r}")


def churn(
    dispatch: dict,
    trial_submissions: list[dict],
    trial_payloads: list[dict],
    memo: list[dict],
) -> list[dict]:
    """Skeletonize a DISHTINY prq49 genome, stage by stage.

    Each stage starts from the positions the stages before it knocked
    out, and adds its own:

    * `strip` runs the sgpl-static pruner, which nops instructions that
      are provably dead. Its nops are taken as they come: no competition
      checks them.
    * `identity:<kind>` searches, by the `hybrid` policy, for the units
      whose knockout shows nothing. The search's test is rundishtiny's
      own: the knockout and the wildtype, each alone in a world, side by
      side until they differ (`divergence`). Its audits, which pace
      themselves, also compete the knockouts so far against the wildtype
      in the worlds of `identity_worlds`, the same in every audit, each
      of which must end bit-identical to the wildtype's own. A world is
      a trial: those of the first size are launched at once, with the
      search's test, and each later size's only if all before it pass.
      A failed audit sifts what was knocked out since, auditing groups
      of it at once: what passes stays out, and a unit that fails alone
      goes back in for good. Nothing is kept that an audit has not
      accepted.
    * `fitness:<kind>` searches, by the `staged` policy, for the units
      whose knockout costs no more than the margin of fitness. A screen
      is one competition of the `screen` size, and fails a knockout whose
      share of cells is under what a wildtype control would fall below
      with probability `screen_error_rate` (`lethal_share`); if the
      search is `two_sided`, also one whose share is as far over the
      controls'. The ranking
      and the first
      confirmation run competitions of the `small` size. The longest
      knockout that confirmation has accepted is confirmed again at the
      `full` size after every few of its acceptances, and where it
      settles: each such test that passes doubles the wait, across
      stages, and each that fails halves it and bounds the search from
      above. The wildtype controls of each size are run once and serve
      every stage.
    * `final` scores the finished skeleton at the `full` size, counting
      the last reconfirmation's competitions among its own where no
      stage has changed the genome since.

    `<kind>` names the stage's units, as `units_of` lists them. The
    stages start from the wildtype with the positions of `knockout` out,
    none by default, as an earlier run's stages left it. A finished
    stage is memoized, so each tick replays only the stage under way.
    rundishtiny ends every competition after a set time (`run_seconds`),
    where it stands, and a run still going `overhead_seconds` later is
    killed. A trial whose run was killed, or cut short where every
    update matters, is inconclusive: it accepts nothing and fails
    nothing, and each stage counts its `inconclusive_trials`. Every
    trial's `weight` is the seconds its runs may take in all, so that
    `trial_batchsize` is the longest a job can run. See
    docs/dishtiny_prq49.md for the assay kwargs.

    Parameters
    ----------
    dispatch : dict
        The dispatch record, with `assay_kwargs`.
    trial_submissions : list of dict
        The dispatch's trial submissions.
    trial_payloads : list of dict
        The dispatch's trial payloads.
    memo : list of dict
        Each finished stage's outcome: its `stage`, the positions it
        `added` to the knockout, and its `summary`.

    Returns
    -------
    list of dict
        This step's actions.

    Raises
    ------
    ValueError
        If a stage is unknown.
    RuntimeError
        If a control of the screen's failed.
    """
    kw = {**DEFAULTS, **dispatch["assay_kwargs"]}
    operations, stages = kw["operations"], list(kw["stages"])
    done = {m["stage"]: m for m in memo}
    knockout: set = set(decode_sites(kw["knockout"]))
    for i, spec in enumerate(stages):
        name = f"{i:02d}:{spec}"
        if name in done:
            knockout |= set(done[name]["added"])
            continue
        trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
        by_key = {canonical_json(t["key"]): t for t in trials}
        actions, outcome = _stage(
            kw,
            name,
            spec,
            knockout,
            dispatch,
            (trial_submissions, trial_payloads),
            by_key,
            done,
        )
        if outcome is not None:
            # trials whose runs were cut short or killed, and show nothing
            unsure = sum(
                isinstance(t["key"], dict)
                and t["key"].get("stage") == name
                and isinstance(t["result"], dict)
                and "inconclusive" in t["result"]
                for t in trials
            )
            outcome["summary"]["inconclusive_trials"] = unsure
            if unsure:
                actions.append(
                    scd_churn.warning(
                        f"{name}: {unsure} trials were inconclusive: their "
                        "runs were cut short or killed at their time limits",
                        dedupe_key=f"{name}:inconclusive",
                    )
                )
            return [*actions, scd_churn.memo({"stage": name, **outcome})]
        notes = [
            a["kwargs"].get("message")
            for a in actions
            if a["action"] == "progress"
        ]
        return [
            *(a for a in actions if a["action"] != "progress"),
            scd_churn.progress(
                i, len(stages), ": ".join(filter(None, [name, *notes]))
            ),
        ]
    live = [
        p
        for p, o in enumerate(operations)
        if p not in knockout and not is_nop(o)
    ]
    return [
        scd_churn.succeed(
            {
                "knockout": encode_sites(knockout),
                "knockout_count": len(knockout),
                "skeleton": encode_sites(live),
                "skeleton_count": len(live),
                "stages": [
                    {
                        "stage": f"{i:02d}:{spec}",
                        "added": len(done[f"{i:02d}:{spec}"]["added"]),
                        "summary": done[f"{i:02d}:{spec}"]["summary"],
                    }
                    for i, spec in enumerate(stages)
                ],
            }
        )
    ]

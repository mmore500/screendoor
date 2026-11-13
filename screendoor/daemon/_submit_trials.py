import hashlib

from ..auxlib._DispatchContext import DispatchContext
from ..auxlib._batch_trials import batch_trials
from ..auxlib._canonical_json import canonical_json


def job_name(ctx: DispatchContext, entries: list[dict]) -> str:
    """Name the job of one launch after the dispatch and the trial attempts
    it runs.

    The name is deterministic, so that the name recorded with each trial
    submission is the name the orchestrator gives the job, and `poke` can
    find it.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch launching.
    entries : list of dict
        The trial attempts launched, each with `trial_uuid` and `attempt`.

    Returns
    -------
    str
        `screendoor-<dispatch uuid prefix>-<digest of the attempts>`.
    """
    pairs = sorted((e["trial_uuid"], e["attempt"]) for e in entries)
    digest = hashlib.sha256(canonical_json(pairs).encode()).hexdigest()
    return f"screendoor-{ctx.dispatch_uuid[:8]}-{digest[:12]}"


def submit_trials(
    ctx: DispatchContext, entries: list[dict], n_trials: int
) -> None:
    """Record a `requested` submission per entry, then launch the entries
    as one job.

    The batches and job are fixed and recorded first, as `job: {"name",
    "index"}` with the index that of the batch (or array task), so that
    `poke` can tell from the records alone which job runs each trial. A
    crash after recording and before launching leaves jobs that `poke`
    finds missing, so they are relaunched. `how_prep_trial_payloads` runs
    before the launch, so that fixed-size storage has room for all
    `n_trials` trials.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch launching.
    entries : list of dict
        One per trial attempt: `trial_uuid` and `attempt`, plus the other
        fields its submission records.
    n_trials : int
        How many trials the dispatch will have once these are submitted.
    """
    if not entries:
        return
    name = job_name(ctx, entries)
    batches = batch_trials(entries, ctx.record["trial_batchsize"])
    for index, batch in enumerate(batches):
        for e in batch:
            ctx.write_trial_submission(
                {
                    "event": "requested",
                    **e,
                    "job": {"name": name, "index": index},
                }
            )
    ctx.call_hook("how_prep_trial_payloads", n_trials)
    ctx.call_hook(
        "how_launch",
        name,
        [
            [
                {"trial_uuid": e["trial_uuid"], "attempt": e["attempt"]}
                for e in b
            ]
            for b in batches
        ],
    )

import hashlib

from ..auxlib._batch_trials import batch_trials
from ..auxlib._canonical_json import canonical_json


def job_name(ctx, entries: list) -> str:
    """The job name for one launch: the dispatch and its trial attempts.

    Deterministic, so the name recorded with each trial submission is the
    name the orchestrator gives the job, and poke can find it.
    """
    pairs = sorted((e["trial_uuid"], e["attempt"]) for e in entries)
    digest = hashlib.sha256(canonical_json(pairs).encode()).hexdigest()
    return f"screendoor-{ctx.dispatch_uuid[:8]}-{digest[:12]}"


def submit_trials(ctx, entries: list, n_trials: int) -> None:
    """Record a ``requested`` submission per entry, then launch them.

    Each entry has ``trial_uuid`` and ``attempt`` plus the fields its
    submission records. The batches and job are fixed and recorded first,
    as ``job: {"name", "index"}`` (index: the batch, or array task), so
    that poke can tell from the records alone which job runs each trial.
    A crash after recording and before launching leaves jobs that poke
    finds missing, so they are relaunched.

    how_prep_trial_payloads runs before the launch, so that fixed-size
    storage has room for all ``n_trials`` trials.
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
    ctx.hook("how_prep_trial_payloads")(ctx, n_trials)
    ctx.hook("how_launch")(
        ctx,
        name,
        [
            [
                {"trial_uuid": e["trial_uuid"], "attempt": e["attempt"]}
                for e in b
            ]
            for b in batches
        ],
    )

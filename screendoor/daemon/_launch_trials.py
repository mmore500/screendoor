import hashlib

from ..auxlib._canonical_json import canonical_json


def make_launch_id(entries: list) -> str:
    """Hash of the (trial_uuid, attempt) pairs one launch call covers."""
    pairs = sorted((e["trial_uuid"], e["attempt"]) for e in entries)
    return hashlib.sha256(canonical_json(pairs).encode()).hexdigest()[:16]


def launch_entries(ctx, entries: list, launch_id: str) -> None:
    """Call how_launch, then record ``launched`` for each trial.

    First how_prep_payload makes room for every trial requested so far, as
    storage that must be sized before its writers start needs.
    """
    if not entries:
        return
    n_trials = len(ctx.hook("how_read_payload")(ctx))
    ctx.hook("how_prep_payload")(ctx, n_trials)
    launch = ctx.hook("how_launch")
    for e in launch(ctx, entries, launch_id):
        ctx.hook("how_write_payload")(
            ctx,
            {
                "event": "launched",
                "trial_uuid": e["trial_uuid"],
                "attempt": e["attempt"],
                "job_id": e["job_id"],
                "launch_id": launch_id,
            },
        )
    if hasattr(launch, "after_launched"):  # the inline launcher runs here
        launch.after_launched(ctx, entries)

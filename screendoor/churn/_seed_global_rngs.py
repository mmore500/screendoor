import functools
import hashlib
import importlib.util
import random
import sys

from ..auxlib._canonical_json import canonical_json


def churn_seed(meta_seed: int, n_memo: int, n_trial_submissions: int) -> int:
    """The 32-bit seed for a churn call, from the dispatch's ``meta_seed``
    and how many memos and trial submissions it has seen so far."""
    parts = [meta_seed, n_memo, n_trial_submissions]
    digest = hashlib.sha256(canonical_json(parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _numpy():
    """numpy, imported if installed and not yet imported; else None."""
    if "numpy" in sys.modules:
        return sys.modules["numpy"]
    if importlib.util.find_spec("numpy") is None:
        return None
    import numpy

    return numpy


def seed_global_rngs(assay):
    """Wrap an assay's churn so that every call first seeds the global RNGs.

    ``random.seed`` and, if numpy is installed, ``numpy.random.seed`` get
    churn_seed(meta_seed, len(memo), len(trial_submissions)). The same
    dispatch state always gives the same draws, so replay_dispatch can
    reproduce a churn call. ``assay`` is a churn function or a module
    with one.

    In a dispatch, wrap the assay expression in a call::

        "assay": "scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)"
    """
    churn = getattr(assay, "churn", assay)

    @functools.wraps(churn)
    def seeded_churn(dispatch, trial_submissions, trial_payloads, memo):
        seed = churn_seed(
            dispatch["meta_seed"], len(memo), len(trial_submissions)
        )
        random.seed(seed)
        numpy = _numpy()
        if numpy is not None:
            numpy.random.seed(seed)
        return churn(dispatch, trial_submissions, trial_payloads, memo)

    return seeded_churn

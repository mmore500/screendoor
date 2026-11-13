import functools
import hashlib
import importlib.util
import random
import sys
import types
import typing

from ..auxlib._canonical_json import canonical_json


def churn_seed(meta_seed: int, n_memo: int, n_trial_submissions: int) -> int:
    """Derive the 32-bit seed of one churn call from the dispatch's
    `meta_seed` and how many memos and trial submissions churn has seen.

    Parameters
    ----------
    meta_seed : int
        The dispatch's seed.
    n_memo : int
        How many memos churn has seen.
    n_trial_submissions : int
        How many trial submissions churn has seen.

    Returns
    -------
    int
        The seed, from 0 to 2**32 - 1.
    """
    parts = [meta_seed, n_memo, n_trial_submissions]
    digest = hashlib.sha256(canonical_json(parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _numpy() -> types.ModuleType | None:
    """Return numpy if it is installed, importing it if need be."""
    if "numpy" in sys.modules:
        return sys.modules["numpy"]
    if importlib.util.find_spec("numpy") is None:
        return None
    import numpy

    return numpy


def seed_global_rngs(
    assay: typing.Callable[..., list[dict]] | types.ModuleType,
) -> typing.Callable[
    [dict, list[dict], list[dict], list[typing.Any]], list[dict]
]:
    """Wrap an assay's churn function so that each call first seeds the
    global random number generators.

    `random.seed` and, if numpy is installed, `numpy.random.seed` are
    called with `churn_seed(meta_seed, len(memo), len(trial_submissions))`.
    The same dispatch state therefore gives the same draws, so that
    `replay_dispatch` can reproduce a churn call.

    In a dispatch, wrap the assay expression in a call::

        "assay": "scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)"

    Parameters
    ----------
    assay : Callable or module
        A churn function, or a module with a `churn` attribute.

    Returns
    -------
    Callable[[dict, list[dict], list[dict], list], list[dict]]
        A churn function that seeds the global generators, then calls the
        assay's churn.
    """
    churn = getattr(assay, "churn", assay)

    @functools.wraps(churn)
    def seeded_churn(
        dispatch: dict,
        trial_submissions: list[dict],
        trial_payloads: list[dict],
        memo: list[typing.Any],
    ) -> list[dict]:
        seed = churn_seed(
            dispatch["meta_seed"], len(memo), len(trial_submissions)
        )
        random.seed(seed)
        numpy = _numpy()
        if numpy is not None:
            numpy.random.seed(seed)
        return churn(dispatch, trial_submissions, trial_payloads, memo)

    return seeded_churn

"""Run one trial of `e2e_skeleton` on a DISHTINY prq49 genome.

`$DISHTINY_MODE` picks the trial, and `$DISHTINY_KNOCKOUT` (positions, as
`0-5,9`) its genome:

* `score`: one competition against the wildtype, of `$DISHTINY_UPDATES`
  by `$DISHTINY_N_CELLS`, on a world seeded from the trial's uuid. Sends
  the genome's share of cells as `score`.
* `screen`: one such competition. Sends `accept`, false if the genome's
  share is not over `$DISHTINY_SCREEN_PASS`, or it is extinct: the
  knockout is lethal.
* `identity`: first rundishtiny's own divergence test, at each
  `[updates, cells, kill_seconds]` of `$DISHTINY_DIVERGENCE`: the genome
  and the wildtype, each alone in a world, side by side until they
  differ. Then, on each `[updates, cells, seed, run_seconds]` of
  `$DISHTINY_WORLDS`, a competition and the wildtype's own against
  itself, until one differs. Sends `accept`, true if nothing differed.
* `strip`: runs the sgpl-static pruner on the genome. Sends the
  positions `pruned`.

rundishtiny ends a competition after `$DISHTINY_RUN_SECONDS` seconds (a
world's own `run_seconds`, in `identity`), where it stands, and the
result is of the updates run: `cut_short` says so. A run still going
`$DISHTINY_OVERHEAD_SECONDS` (default 10) later is killed. A run that
was cut short where all its updates matter, or killed, shows nothing,
and its trial is `inconclusive`: an identity trial does not accept, a
screen does not fail, and a score is not `viable`. The pruner is killed
after `$DISHTINY_PRUNER_TIMEOUT` seconds, and its trial fails.
A competition on a fixed world always ends the same, so it is kept in
`$DISHTINY_CACHE`, if set. `compete` lists the simulation's variables.
The pruner runs as `$DISHTINY_PRUNER` (default: its v0.3.2 image by
singularity; `{dir}` stands for the working directory, to mount), on
`$DISHTINY_PROJECT` with `$DISHTINY_PERIPHERAL`.
"""

import hashlib
import json
import os
import random
import resource
import shlex
import subprocess
import sys
import tempfile
import typing

from ...auxlib._decode_sites import decode_sites
from ._compete import Inconclusive, compete, diverges, knocked_out

PRUNER = (
    "singularity run --cleanenv docker://ghcr.io/mmore500/sgpl-static:v0.3.2"
)
PROJECT = (
    "https://github.com/mmore500/dishtiny"
    "@978abb3e1839820b77693490d34d8ce88e4fba2d"
)
PERIPHERAL = (
    "https://raw.githubusercontent.com/mmore500/sgpl-static/"
    "380be308d15554931d4dcfa476022eff300573ee/"
    "peripherals/dishtiny/prq49-as-of-2026-11-14.hpp"
)
# the subset of -O2 the pruner's README suggests: effective, and fast
OPTFLAGS = (
    "-passes=function(early-cse,instcombine<no-verify-fixpoint>),"
    "cgscc(devirt<4>(inline,function<eager-inv;no-rerun>(sroa,"
    "early-cse<memssa>,simplifycfg<switch-range-to-icmp>,"
    "loop(loop-unroll-full),sroa,gvn,bdce,jump-threading))),deadargelim,"
    "function(loop(loop-deletion),instcombine<no-verify-fixpoint>,"
    "simplifycfg<forward-switch-cond;switch-range-to-icmp;"
    "hoist-common-insts;sink-common-insts>,instcombine<no-verify-fixpoint>),"
    "globaldce"
)


def _size() -> tuple[int, int]:
    return (
        int(os.environ["DISHTINY_UPDATES"]),
        int(os.environ["DISHTINY_N_CELLS"]),
    )


def _limits(run_seconds: int | None = None) -> dict:
    """Give a competition's time limits: when rundishtiny ends it, and
    when it is killed, a little later."""
    if run_seconds is None:
        run_seconds = int(os.environ.get("DISHTINY_RUN_SECONDS", "0"))
    overhead = float(os.environ.get("DISHTINY_OVERHEAD_SECONDS", "10"))
    return {
        "run_seconds": run_seconds,
        "kill_seconds": run_seconds + overhead if run_seconds else None,
    }


def _trial_seed() -> int:
    """Seed a world from the trial's uuid, so that replicates draw their
    own worlds and a replayed dispatch draws the same ones."""
    trial = os.path.basename(os.environ.get("SCREENDOOR_TRIAL_DIR", ""))
    if not trial:
        return random.SystemRandom().randrange(2**62)
    digest = hashlib.sha256(trial.encode()).digest()
    return int.from_bytes(digest[:8], "big") >> 2


def fixed(
    knockout: set[int],
    seed: int,
    size: tuple[int, int],
    *,
    census: bool,
    run_seconds: int | None = None,
) -> dict:
    """Run a competition on a fixed world, or recall it from
    `$DISHTINY_CACHE`.

    Parameters
    ----------
    knockout : set of int
        Program positions to knock out of the candidate.
    seed : int
        The world's seed.
    size : tuple of int
        Updates to run, and cells.
    census : bool
        Whether to fingerprint the end state.
    run_seconds : int or None, default None
        Seconds after which the run ends where it stands; 0 for no limit,
        None for `$DISHTINY_RUN_SECONDS`.

    Returns
    -------
    dict
        The competition's result, as `compete` gives it.

    Raises
    ------
    Inconclusive
        If the run was cut short, or killed: how far it got depends on
        the node, so it is not the world to compare, nor to keep.
    """
    cache = os.environ.get("DISHTINY_CACHE")

    def run() -> dict:
        result = compete(
            knockout, seed, size, census=census, **_limits(run_seconds)
        )
        if result["cut_short"]:
            raise Inconclusive(f"a fixed world of {size} was cut short")
        return result

    if not cache:
        return run()
    text = json.dumps([sorted(knockout), seed, list(size), census])
    name = hashlib.sha256(text.encode()).hexdigest()[:32] + ".json"
    path = os.path.join(cache, name[:2], name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    result = run()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=os.path.dirname(path), suffix=".tmp", delete=False
    ) as fh:
        json.dump(result, fh)
    os.replace(fh.name, path)  # whole, or not there
    return result


def _outcome(result: dict) -> tuple:
    return (
        result["candidate_count"],
        result["wildtype_count"],
        result["fingerprint"],
    )


def score(knockout: set[int]) -> dict:
    """Compete on a world of the trial's own; a run that had to be killed
    is not `viable`."""
    try:
        return compete(knockout, _trial_seed(), _size(), **_limits())
    except Inconclusive as e:
        return {"score": 0.0, "viable": False, "inconclusive": str(e)}


def screen(knockout: set[int]) -> dict:
    """Compete on a world of the trial's own, and fail a genome whose
    share of cells is not over `$DISHTINY_SCREEN_PASS`, or is none. A run
    that had to be killed fails nothing."""
    result = score(knockout)
    if "inconclusive" in result:
        return {**result, "accept": True}
    least = max(float(os.environ["DISHTINY_SCREEN_PASS"]), 0.0)
    return {**result, "accept": result["score"] > least}


def identity(knockout: set[int], worlds: list[list[int]]) -> dict:
    """Tell whether the genome runs as the wildtype does: by rundishtiny's
    divergence test, at each size in `$DISHTINY_DIVERGENCE`, then by
    whether each world's competition ends as the wildtype's own does.
    It stops at the first difference; a run cut short or killed shows
    nothing, and the genome is not accepted."""
    same = 0
    try:
        tiers = json.loads(os.environ.get("DISHTINY_DIVERGENCE", "[]"))
        for tier, (updates, cells, kill_seconds) in enumerate(tiers):
            if diverges(knockout, (updates, cells), kill_seconds=kill_seconds):
                return {"accept": False, "identical": 0, "diverged": tier}
        for updates, cells, seed, *limit in worlds:
            run = {"census": True, "run_seconds": limit[0] if limit else 0}
            ours = fixed(knockout, seed, (updates, cells), **run)
            theirs = fixed(set(), seed, (updates, cells), **run)
            if _outcome(ours) != _outcome(theirs):
                break
            same += 1
    except Inconclusive as e:
        return {"accept": False, "identical": same, "inconclusive": str(e)}
    return {"accept": same == len(worlds), "identical": same}


def prune(knockout: set[int]) -> list[int]:
    """Run the sgpl-static pruner on the knocked-out genome, and list the
    positions it nopped."""
    with open(os.environ["DISHTINY_GENOME"], encoding="utf-8") as fh:
        before = knocked_out(json.load(fh), knockout)
    work = tempfile.mkdtemp(prefix="prune_", dir=os.getcwd())
    with open(os.path.join(work, "in.json"), "w", encoding="utf-8") as fh:
        json.dump(before, fh)
    pruner = os.environ.get("DISHTINY_PRUNER", PRUNER).replace("{dir}", work)
    subprocess.run(
        [
            *shlex.split(pruner),
            *("--input", "in.json", "--input-key", "value0.program"),
            *("--project", os.environ.get("DISHTINY_PROJECT", PROJECT)),
            "--peripheral",
            os.environ.get("DISHTINY_PERIPHERAL", PERIPHERAL),
            "--cxxflags",
            "-Iinclude -Ithird-party/signalgp-lite/include",
            *("--solver", "stride711-split", "--optflags", OPTFLAGS),
            *("--output", "out.json"),
        ],
        cwd=work,
        check=True,
        stdout=sys.stderr,
        timeout=float(os.environ.get("DISHTINY_PRUNER_TIMEOUT", "0")) or None,
    )
    with open(os.path.join(work, "out.json"), encoding="utf-8") as fh:
        after = json.load(fh)
    was, now = before["value0"]["program"], after["value0"]["program"]
    if len(was) != len(now) or any(
        a["args"] != b["args"] or a["bitstring"] != b["bitstring"]
        for a, b in zip(was, now)
    ):
        raise RuntimeError("the pruner changed more than operations")
    return [
        i
        for i, (a, b) in enumerate(zip(was, now))
        if a["operation"] != b["operation"]
    ]


def run(mode: str, knockout: set[int], worlds: typing.Any) -> dict:
    """Run a trial of one mode; see the module's docstring.

    Parameters
    ----------
    mode : str
        `score`, `screen`, `identity` or `strip`.
    knockout : set of int
        Program positions knocked out.
    worlds : Any
        The trial's worlds, as its mode reads `$DISHTINY_WORLDS`.

    Returns
    -------
    dict
        The trial's result.

    Raises
    ------
    ValueError
        If `mode` is unknown.
    RuntimeError
        If rundishtiny or the pruner fails.
    """
    if mode == "score":
        return score(knockout)
    if mode == "screen":
        return screen(knockout)
    if mode == "identity":
        return identity(knockout, worlds)
    if mode == "strip":
        return {"pruned": prune(knockout)}
    raise ValueError(f"unknown DISHTINY_MODE {mode!r}")


def main() -> int:
    """Run the trial the environment describes, and send its result with
    the CPU seconds its competitions took as `cpu_s`."""
    result = run(
        os.environ["DISHTINY_MODE"],
        decode_sites(os.environ.get("DISHTINY_KNOCKOUT", "")),
        json.loads(os.environ.get("DISHTINY_WORLDS", "null")),
    )
    used = resource.getrusage(resource.RUSAGE_CHILDREN)
    result["cpu_s"] = used.ru_utime + used.ru_stime
    print("!!!screendoor:payload " + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

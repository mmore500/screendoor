import contextlib
import csv
import glob
import hashlib
import json
import lzma
import os
import random
import shutil
import stat
import subprocess
import tempfile
import typing

from ._ops import RNG_NOPS

NOP = "Nop-0"
# the quorum and resource-harvest settings of the prq49 competitions, with
# mutation off
PRQ49 = {
    "MUTATION_RATE": "0.0 0.0 0.0",
    "COLLECTIVE_HARVEST_RATE": "0.0 0.25",
    "GROUP_EXPIRATION_DURATIONS": "0 1024",
    "OPTIMAL_QUORUM_COUNT": "0 12",
    "P_QUORUM_CAP_KILL": "0.0 0.0825",
    "P_SET_QUORUM_BIT": "0.0 1.0",
    "QUORUM_CAP": "0 36",
}


def knocked_out(genome: dict, knockout: set[int]) -> dict:
    """Copy a genome with the instructions at `knockout` turned into nops.

    An instruction that draws random numbers becomes the nop that draws
    as many (`RNG_NOPS`), so the knockout leaves the random number stream
    as it was; any other becomes `Nop-0`. Arguments, tags and the
    program's length stay.

    Parameters
    ----------
    genome : dict
        A DISHTINY genome, with its program at `value0.program`.
    knockout : set of int
        Positions in the program.

    Returns
    -------
    dict
        The genome, sharing what did not change.
    """
    program = [
        {
            **inst,
            "operation": (
                RNG_NOPS.get(inst["operation"], NOP)
                if i in knockout
                else inst["operation"]
            ),
            "descriptors": [],
        }
        for i, inst in enumerate(genome["value0"]["program"])
    ]
    return {**genome, "value0": {**genome["value0"], "program": program}}


def _shims(parent: str) -> str:
    """Make no-op stand-ins for the utilities rundishtiny shells out to."""
    path = os.path.join(parent, "shims")
    os.makedirs(path)
    for name in ("tree", "keyname", "python3", "md5sum"):
        shim = os.path.join(path, name)
        with open(shim, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR)
    return path


def _census(outdata: str) -> str:
    """Hash the end-state cell census: each cell's age, kin groups,
    resource stockpile, root id and spawn count."""
    (path,) = glob.glob(os.path.join(outdata, "a=cell_census*"))
    with lzma.open(path, "rt", encoding="utf-8") as fh:
        rows = sorted(
            (r["Metric"], r["Cell"], r["Update"], r["Value"])
            for r in csv.DictReader(fh)
        )
    if not rows:
        raise RuntimeError("rundishtiny wrote an empty cell census")
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


class Inconclusive(RuntimeError):
    """rundishtiny had to be killed, so its run shows nothing."""


@contextlib.contextmanager
def rundishtiny(
    knockouts: dict[int, set[int]],
    flags: list[str],
    kill_seconds: float | None = None,
) -> typing.Iterator[str]:
    """Run rundishtiny on the wildtype genome's knockouts, one per root
    id, and yield the directory of its output files.

    The run reads `$DISHTINY_BINARY` (rundishtiny), `$DISHTINY_GENOME`
    (the wildtype genome's JSON), `$DISHTINY_CONFIG` (dishtiny.cfg) and,
    if set, `$DISHTINY_SERIES` and `$DISHTINY_STINT`.

    Parameters
    ----------
    knockouts : dict of {int: set of int}
        The program positions knocked out of each root id's genome.
    flags : list of str
        Command line flags, after those every run takes.
    kill_seconds : float or None, default None
        Seconds after which a run still going is killed; None for never.

    Raises
    ------
    Inconclusive
        If the run was killed.
    RuntimeError
        If rundishtiny fails.
    """
    with open(os.environ["DISHTINY_GENOME"], encoding="utf-8") as fh:
        genome = json.load(fh)
    cmd = [
        os.environ["DISHTINY_BINARY"],
        *("-N_THREADS", "1", "-GENESIS", "innoculate", "-WEAK_SCALING", "0"),
        *(part for key, value in PRQ49.items() for part in (f"-{key}", value)),
        *("-DIVERSITY_MAINTENANCE_SERVICE_FREQUENCY", "0"),
        *("-STINT", " " + os.environ.get("DISHTINY_STINT", "100")),
        *("-SERIES", " " + os.environ.get("DISHTINY_SERIES", "16005")),
        *("-THROW_ON_EXTINCTION", "0"),
        *("-PHENOTYPE_EQUIVALENT_NOPOUT_LOWEST_ROOT", "0"),
        *flags,
    ]
    with tempfile.TemporaryDirectory(prefix="dishtiny_prq49_") as tmp:
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        shutil.copyfile(
            os.environ["DISHTINY_CONFIG"], os.path.join(work, "dishtiny.cfg")
        )
        for root_id, knockout in knockouts.items():
            path = os.path.join(work, f"root_id={root_id}+a=genome+ext=.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    knocked_out(genome, knockout), fh, separators=(",", ":")
                )
        path = _shims(tmp) + os.pathsep + os.environ.get("PATH", "")
        try:
            proc = subprocess.run(
                cmd,
                cwd=work,
                env={**os.environ, "PATH": path},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=kill_seconds,
            )
        except subprocess.TimeoutExpired:
            raise Inconclusive(
                f"rundishtiny was killed after {kill_seconds} seconds"
            ) from None
        if proc.returncode != 0:
            raise RuntimeError(
                f"rundishtiny exited {proc.returncode}: "
                + proc.stderr.decode(errors="replace")[-2000:]
            )
        yield os.path.join(work, "outdata")


def _result_file(outdata: str, what: str) -> str:
    """Find rundishtiny's output file of one kind."""
    found = [
        p
        for p in glob.glob(os.path.join(outdata, f"*a={what}*+ext=.csv"))
        if "@longlink" not in os.path.basename(p)
    ]
    if not found:
        raise RuntimeError(f"rundishtiny wrote no {what} csv")
    return found[0]


def diverges(
    knockout: set[int],
    size: tuple[int, int],
    *,
    kill_seconds: float | None = None,
) -> bool:
    """Tell whether a knockout genome's world diverges from the wildtype's.

    This is rundishtiny's own test (`TEST_INTERROOT_PHENOTYPE_
    DIFFERENTIATION`): the wildtype and the knockout each seed a world of
    their own, with no one else in it, and the two run update by update on
    the same random numbers until any cell's resource stockpile differs.
    A knockout that diverges ends the run at once.

    Parameters
    ----------
    knockout : set of int
        Program positions to knock out.
    size : tuple of int
        The most updates to run, and cells.
    kill_seconds : float or None, default None
        Seconds after which a run still going is killed; None for never.

    Returns
    -------
    bool
        Whether the worlds diverged within the updates.

    Raises
    ------
    Inconclusive
        If the run was killed.
    RuntimeError
        If rundishtiny fails, or writes no result.
    """
    flags = [
        # the test runs in place of the run; it needs a root id 0
        *("-RUN", "0", "-N_CELLS", str(size[1]), "-RNG_PRESEED", "1"),
        *(
            "--REPLICATE",
            "1",
            "-TEST_INTERROOT_PHENOTYPE_DIFFERENTIATION",
            "1",
        ),
        *("-PHENOTYPIC_DIVERGENCE_N_UPDATES", str(size[0])),
    ]
    with rundishtiny({0: set(), 1: knockout}, flags, kill_seconds) as outdata:
        path = _result_file(outdata, "interroot_phenotype_differentiation")
        with open(path, encoding="utf-8") as fh:
            (row,) = csv.DictReader(fh)
    return bool(int(row["Phenotype Divergence Detected"]))


def compete(
    knockout: set[int],
    seed: int,
    size: tuple[int, int],
    *,
    census: bool = False,
    run_seconds: int = 0,
    kill_seconds: float | None = None,
) -> dict:
    """Run one competition of a knockout genome against the wildtype.

    Both are inoculated into one `rundishtiny` world, and the score is
    the candidate's share of the cells at the end, 0.5 if it is neutral.
    Root ids are permuted from the seed, so that neither is favoured. A
    world is deterministic: the same knockout, seed and size end the same.

    Parameters
    ----------
    knockout : set of int
        Program positions to knock out of the candidate.
    seed : int
        The world's seed.
    size : tuple of int
        Updates to run, and cells.
    census : bool, default False
        Whether to also dump and hash every cell's end state, as
        `fingerprint`: two runs with the same hash and counts ended in
        the same world.
    run_seconds : int, default 0
        Seconds after which rundishtiny ends the run where it stands
        (its `RUN_SECONDS`), short of `size`'s updates; 0 for no limit.
    kill_seconds : float or None, default None
        Seconds after which a run still going is killed; None for never.

    Returns
    -------
    dict
        `score`, `candidate_count`, `wildtype_count`, `seed`, the
        `updates` run, whether the run was `cut_short` by `run_seconds`
        with both sides alive and, with `census`, `fingerprint`.

    Raises
    ------
    Inconclusive
        If the run was killed.
    RuntimeError
        If rundishtiny fails, or writes no result.
    """
    rng = random.Random(seed)
    preseed = rng.randrange(1, 2**31 - 1)
    root_ids = [1, 2]  # entrant 0 is the wildtype, 1 the candidate
    rng.shuffle(root_ids)
    flags = [
        *("-RUN_UPDATES", str(size[0]), "-RUN_SECONDS", str(int(run_seconds))),
        *("-N_CELLS", str(size[1]), "-RNG_PRESEED", str(preseed)),
        *("--REPLICATE", str(preseed), "-ABORT_IF_COALESCENT_FREQ", "64"),
        *(("-DATA_DUMP", "1", "-CENSUS_WRITE", "1") if census else ()),
    ]
    knockouts = {root_ids[0]: set(), root_ids[1]: knockout}
    with rundishtiny(knockouts, flags, kill_seconds) as outdata:
        counts, updates = {1: 0, 2: 0}, 0
        with open(
            _result_file(outdata, "coalescence_result"), encoding="utf-8"
        ) as fh:
            for row in csv.DictReader(fh):
                root_id = int(float(row["Root ID"]))
                updates = int(float(row["Update"]))
                if root_id in counts:
                    counts[root_id] = int(float(row["Count"]))
        fingerprint = {"fingerprint": _census(outdata)} if census else {}
    wildtype, candidate = counts[root_ids[0]], counts[root_ids[1]]
    total = wildtype + candidate
    return {
        "score": candidate / total if total else 0.0,
        "candidate_count": candidate,
        "wildtype_count": wildtype,
        "seed": seed,
        "updates": updates,
        # a run also ends early, by design, once one side is gone
        "cut_short": updates < size[0] and min(wildtype, candidate) > 0,
        **fingerprint,
    }

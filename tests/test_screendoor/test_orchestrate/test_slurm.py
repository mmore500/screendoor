"""Slurm hooks against recorded command output (no cluster needed)."""

import pytest

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.auxlib._default_python_command import (
    default_python_command,
)
from screendoor.daemon import (
    _apply_actions,
    kill_dispatch,
    resume_dispatch,
    run_tick_once,
    submit_dispatch,
)
from screendoor.daemon.slurm import (
    cancel_chain,
    render_daemon_sbatch,
    submit_daemon,
)
from screendoor.orchestrate.slurm import _run_slurm_command as rsc
from screendoor.orchestrate.slurm._render_sbatch import parse_batches


class FakeSlurm:
    """Stands in for the Slurm commands, with a queue tests can edit."""

    def __init__(self):
        self.calls = []  # every argv run
        self.queue = set()  # job ids, one per array task
        self.scripts = {}  # job id -> submitted script

    def count(self, cmd):
        return sum(argv[0] == cmd for argv in self.calls)

    def run(self, argv):
        self.calls.append(argv)
        cmd = argv[0]
        if cmd == "sbatch":
            with open(argv[-1]) as fh:
                script = fh.read()
            jid = 1000 + len(self.scripts)
            self.scripts[jid] = script
            for i in range(len(parse_batches(script) or [None])):
                self.queue.add(f"{jid}_{i}")
            return f"{jid};cluster\n"
        if cmd == "squeue":
            name = next(
                (a.split("=", 1)[1] for a in argv if a.startswith("--name=")),
                None,
            )
            ids = sorted(self.queue)
            if name:
                ids = [
                    i
                    for i in ids
                    if name in self.scripts.get(int(i.split("_")[0]), "")
                ]
            start = "|N/A" if "--format=%i|%S" in argv else ""
            return "".join(f"{i}{start}\n" for i in ids)
        if cmd == "sacct":
            return "1000_0|COMPLETED|0:0\n"
        if cmd == "scancel":
            self.queue -= set(argv[1:])
            return ""
        if cmd == "scontrol":
            return ""
        raise AssertionError(argv)


@pytest.fixture
def slurm(monkeypatch):
    fake = FakeSlurm()
    monkeypatch.setattr(rsc, "run", fake.run)
    return fake


def _submit(workdir, **kw):
    return submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 5},
            "schedule": "* * * * *",
            "trial_batchsize": 2,
            "trial_batch_timeout": 3600,
            "how_launch": "scd.orchestrate.slurm.launch(sbatch_flags="
            "'--partition=standard --mem=8G')",
            "how_poke": "scd.orchestrate.slurm.poke()",
            "how_throttle": "scd.orchestrate.slurm.throttle(max_jobs=500)",
            **kw,
        },
        workdir,
    )


def test_array_submission_and_rendering(workdir, clock, slurm):
    _submit(workdir)
    run_tick_once(workdir)
    (sb,) = [c for c in slurm.calls if c[0] == "sbatch"]
    assert sb[:4] == [
        "sbatch",
        "--parsable",
        "--partition=standard",
        "--mem=8G",
    ]
    script = slurm.scripts[1000]
    assert "#SBATCH --array=0-2" in script
    assert "#SBATCH --time=60" in script
    assert "#SBATCH --job-name=screendoor-" in script
    assert 'cp "$0" ~/slurmscripts/"$SLURM_JOB_ID".sh' in script
    assert "tee -a ~/slurmlogs/" in script
    assert "python3 -m screendoor.worker --workdir" in script
    batches = parse_batches(script)
    assert [len(b) for b in batches] == [2, 2, 1]
    (ctx,) = load_dispatches(workdir)
    jobs = sorted({t["job_id"] for t in ctx.hook("how_read_payload")(ctx)})
    assert jobs == ["1000_0", "1000_1", "1000_2"]


def test_one_squeue_per_tick_and_relaunch(workdir, clock, slurm):
    _submit(workdir)
    run_tick_once(workdir)
    slurm.calls.clear()
    clock.sleep(61)
    run_tick_once(workdir)  # still queued: nothing to do
    assert slurm.count("squeue") == 2  # one poke + one throttle check
    slurm.queue.discard("1000_1")  # preempted, no result
    slurm.calls.clear()
    clock.sleep(61)
    run_tick_once(workdir)
    (ctx,) = load_dispatches(workdir)
    trials = ctx.hook("how_read_payload")(ctx)
    relaunched = [t for t in trials if t["attempt"] == 1]
    assert len(relaunched) == 2  # both trials of batch 1
    assert {t["job_id"] for t in relaunched} == {"1001_0"}  # one new job
    assert slurm.count("sacct") == 1
    assert slurm.count("sbatch") == 1


def test_throttle(workdir, clock, slurm):
    slurm.queue.update(f"9_{i}" for i in range(3))
    _submit(workdir, how_throttle="scd.orchestrate.slurm.throttle(max_jobs=3)")
    run_tick_once(workdir)
    assert slurm.count("sbatch") == 0


def test_adopt_existing_job(workdir, clock, slurm, monkeypatch):
    def die(ctx, entries, launch_id):
        ctx.hook("how_launch")(ctx, entries, launch_id)  # the job starts...
        raise KeyboardInterrupt  # ...and the daemon dies before recording it

    _submit(workdir)
    with monkeypatch.context() as patch:
        patch.setattr(_apply_actions, "launch_entries", die)
        with pytest.raises(KeyboardInterrupt):
            run_tick_once(workdir)
    clock.sleep(61)
    run_tick_once(workdir)
    assert slurm.count("sbatch") == 1  # adopted, not submitted again
    (ctx,) = load_dispatches(workdir)
    assert {t["status"] for t in ctx.hook("how_read_payload")(ctx)} == {
        "launched"
    }


def test_kill_cancels_jobs_and_resume_relaunches(workdir, clock, slurm):
    _submit(workdir, how_kill="scd.orchestrate.slurm.kill()")
    run_tick_once(workdir)
    kill_dispatch(workdir)
    (scancel,) = [c for c in slurm.calls if c[0] == "scancel"]
    assert scancel[1:] == ["1000_0", "1000_1", "1000_2"]
    assert not slurm.queue
    clock.sleep(61)
    assert run_tick_once(workdir) == [] and slurm.count("sbatch") == 1
    resume_dispatch(workdir)
    run_tick_once(workdir)
    assert slurm.count("sbatch") == 2
    (ctx,) = load_dispatches(workdir)
    trials = ctx.hook("how_read_payload")(ctx)
    assert {(t["status"], t["attempt"], t["kills"]) for t in trials} == {
        ("launched", 1, 1)
    }


def test_positional_hook_call_fails_at_setup(workdir, clock, slurm):
    _submit(workdir, how_throttle="scd.orchestrate.slurm.throttle(5)")
    run_tick_once(workdir)
    (ctx,) = load_dispatches(workdir)
    (setup,) = [
        e for e in ctx.wdhooks.read_dispatch(workdir) if e["event"] == "setup"
    ]
    assert "error" in setup["hooks"]["how_throttle"]


def test_daemon_chain(workdir, clock, slurm):
    assert submit_daemon(workdir) is None  # nothing open: no chain
    _submit(workdir)
    jid = submit_daemon(workdir, sbatch_flags="--partition=x")
    assert jid == "1000"
    script = slurm.scripts[1000]
    for needle in (
        "--dependency=singleton",
        "--signal=B:USR1@300",
        "screendoor-daemon-",
        "submit_daemon --successor",
        "run_tick_once",
    ):
        assert needle in script
    assert script == render_daemon_sbatch(
        workdir, python=default_python_command(), sbatch_flags="--partition=x"
    )
    (sbatch,) = [c for c in slurm.calls if c[0] == "sbatch"]
    assert any(a.startswith("--begin=") for a in sbatch)


def test_cancel_chain_only_when_nothing_is_active(workdir, clock, slurm):
    _submit(workdir)
    submit_daemon(workdir)  # queues the daemon job, as 1000_0
    cancel_chain(workdir)
    assert slurm.count("scancel") == 0
    kill_dispatch(workdir)
    cancel_chain(workdir)
    assert slurm.calls[-1] == ["scancel", "1000_0"]

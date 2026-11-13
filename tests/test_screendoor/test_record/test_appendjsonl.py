"""scd.record.appendjsonl with lock=True: appends and reads under fcntl
locks."""

import json
import multiprocessing
import os
import threading

import pytest

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.record import appendjsonl as aj
from screendoor.record.appendjsonl._files import append, read
from screendoor.testing import simulate_dispatch, write_dispatchdir_hooks


def _hold_lock(path, ready, release):
    with aj.locked_open(path, os.O_RDWR | os.O_CREAT, exclusive=True):
        ready.set()
        release.wait(30)


@pytest.fixture
def held(tmp_path):
    """A file whose exclusive lock another process holds."""
    path = str(tmp_path / "x.jsonl")
    ctx = multiprocessing.get_context("fork")
    ready, release = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=_hold_lock, args=(path, ready, release))
    proc.start()
    assert ready.wait(30)
    yield path, release
    release.set()
    proc.join(30)


def test_append_and_read_round_trip(tmp_path):
    path = str(tmp_path / "sub" / "x.jsonl")
    assert read(path, lock=True) == []
    out = append(path, {"event": "hello", "v": 1}, lock=True)
    assert "ts" in out
    assert read(path, lock=True) == [out]
    assert read(path) == [out]  # the same file, locked or not
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_other_process_lock_blocks_writers_and_readers(held):
    path, release = held
    with pytest.raises(aj.LockTimeoutError):
        append(path, {"event": "x"}, lock=True, timeout=0.2)
    with pytest.raises(aj.LockTimeoutError):
        read(path, lock=True, timeout=0.2)
    release.set()
    append(path, {"event": "x"}, lock=True, timeout=30)
    assert [e["event"] for e in read(path, lock=True)] == ["x"]


def test_threads_of_one_process_exclude_each_other(tmp_path):
    path = str(tmp_path / "x.jsonl")
    errors = []
    with aj.locked_open(path, os.O_RDWR | os.O_CREAT, exclusive=True):

        def try_append():
            try:
                append(path, {"event": "x"}, lock=True, timeout=0.2)
            except aj.LockTimeoutError as e:
                errors.append(e)

        thread = threading.Thread(target=try_append)
        thread.start()
        thread.join()
    assert len(errors) == 1 and read(path, lock=True) == []


def test_unterminated_last_line_is_not_spliced(tmp_path):
    path = str(tmp_path / "x.jsonl")
    append(path, {"event": "a"}, lock=True)
    with open(path, "ab") as fh:
        fh.write(b'{"event":"torn","v":')  # a writer that died mid-line
    append(path, {"event": "b"}, lock=True)
    assert [e["event"] for e in read(path, lock=True)] == ["a", "b"]


def _append_many(path, k):
    for j in range(50):
        record = {"event": "big", "k": k, "j": j, "pad": "x" * 200_000}
        append(path, record, lock=True)


def test_concurrent_processes_keep_every_line_whole(tmp_path):
    path = str(tmp_path / "x.jsonl")
    ctx = multiprocessing.get_context("fork")
    procs = [
        ctx.Process(target=_append_many, args=(path, k)) for k in range(8)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
        assert p.exitcode == 0
    with open(path, "rb") as fh:
        rows = [json.loads(line) for line in fh.read().splitlines()]
    assert sorted((r["k"], r["j"]) for r in rows) == [
        (k, j) for k in range(8) for j in range(50)
    ]


LOCKED = {
    f"how_{op}_{f}": f"scd.record.appendjsonl.{op}_{f}(lock=True)"
    for op in ("read", "write")
    for f in (
        "trial_submissions",
        "trial_payloads",
        "trial_telemetry",
        "churn_memo",
        "churn_notify",
    )
}


def test_dispatch_recorded_through_locked_hooks(tmp_path):
    write_dispatchdir_hooks(
        str(tmp_path),
        **{
            f"how_{op}_dispatch_{f}": f"scd.record.appendjsonl."
            f"{op}_dispatch_{f}(lock=True)"
            for op in ("read", "write")
            for f in ("submissions", "payloads", "telemetry")
        },
    )
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {
            "n": 4,
            "cmd": 'echo "!!!screendoor:telemetry $i"; '
            'echo "!!!screendoor:payload $((i + 1))"',
        },
        dispatchdir=str(tmp_path),
        **LOCKED,
    )
    assert r["completed"]["outcome"] == "succeeded"
    assert [t["result"] for t in r["trials"]] == [1, 2, 3, 4]
    (ctx,) = load_dispatches(str(tmp_path))
    assert (
        ctx.record["how_write_trial_payloads"]
        == LOCKED["how_write_trial_payloads"]
    )
    telemetry = ctx.read_trial_telemetry()
    assert {e["event"] for e in telemetry} == {"started", "telemetry"}
    values = [e["value"] for e in telemetry if e["event"] == "telemetry"]
    assert sorted(values) == [0, 1, 2, 3]

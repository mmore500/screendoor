"""scd.record.lockedjsonl: appends and reads under fcntl locks."""

import json
import multiprocessing
import os
import threading

import pytest

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.record import lockedjsonl as lj
from screendoor.record.lockedjsonl._files import append, read_events
from screendoor.testing import simulate_dispatch


def _hold_lock(path, ready, release):
    with lj.locked_open(path, os.O_RDWR | os.O_CREAT, exclusive=True):
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
    assert read_events(path) == []
    out = append(path, {"event": "hello", "v": 1})
    assert out["schema"] == 1 and "ts" in out
    assert read_events(path) == [out]
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_other_process_lock_blocks_writers_and_readers(held):
    path, release = held
    with pytest.raises(lj.LockTimeoutError):
        append(path, {"event": "x"}, timeout=0.2)
    with pytest.raises(lj.LockTimeoutError):
        read_events(path, timeout=0.2)
    release.set()
    append(path, {"event": "x"}, timeout=30)
    assert [e["event"] for e in read_events(path)] == ["x"]


def test_threads_of_one_process_exclude_each_other(tmp_path):
    path = str(tmp_path / "x.jsonl")
    errors = []
    with lj.locked_open(path, os.O_RDWR | os.O_CREAT, exclusive=True):

        def try_append():
            try:
                append(path, {"event": "x"}, timeout=0.2)
            except lj.LockTimeoutError as e:
                errors.append(e)

        thread = threading.Thread(target=try_append)
        thread.start()
        thread.join()
    assert len(errors) == 1 and read_events(path) == []


def test_unterminated_last_line_is_not_spliced(tmp_path):
    path = str(tmp_path / "x.jsonl")
    append(path, {"event": "a"})
    with open(path, "ab") as fh:
        fh.write(b'{"event":"torn","v":')  # a writer that died mid-line
    append(path, {"event": "b"})
    assert [e["event"] for e in read_events(path)] == ["a", "b"]


def _append_many(path, k):
    for j in range(50):
        append(path, {"event": "big", "k": k, "j": j, "pad": "x" * 200_000})


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
    f"how_{op}_{f}": f"scd.record.lockedjsonl.{op}_{f}()"
    for op in ("read", "write")
    for f in ("payload", "memo", "notify", "telemetry")
} | {"how_prep_payload": "scd.record.lockedjsonl.prep_payload()"}


def test_dispatch_recorded_through_locked_hooks(tmp_path):
    with open(tmp_path / "screendoor.json", "w") as fh:
        json.dump(
            {
                "how_read_dispatch": "scd.record.lockedjsonl.read_dispatch()",
                "how_write_dispatch": "scd.record.lockedjsonl.write_dispatch()",
            },
            fh,
        )
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {
            "n": 4,
            "cmd": 'echo "!!!screendoor:telemetry $i"; '
            'echo "!!!screendoor:result $((i + 1))"',
        },
        workdir=str(tmp_path),
        **LOCKED,
    )
    assert r["closed"]["outcome"] == "succeeded"
    assert [t["result"] for t in r["trials"]] == [1, 2, 3, 4]
    (ctx,) = load_dispatches(str(tmp_path))
    assert ctx.hook_expr("how_write_payload") == LOCKED["how_write_payload"]
    telemetry = ctx.hook("how_read_telemetry")(ctx)
    assert {e["event"] for e in telemetry} == {"telemetry"}
    assert sorted(e["value"] for e in telemetry) == [0, 1, 2, 3]

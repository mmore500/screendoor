"""The Slotted JSONL v0.1 conformance tests, C1 to C14."""

from concurrent.futures import ThreadPoolExecutor
import json
import os

import pytest

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from screendoor.record import slottedjsonl as sj
from screendoor.testing import simulate_dispatch

SLOT = sj.DEFAULT_SLOT


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / "run.slots.jsonl")
    sj.init(p, 10)
    return p


def lines(path):
    """Every line, parsed with a plain JSON parser."""
    with open(path, "rb") as fh:
        return [json.loads(line) for line in fh.read().splitlines()]


def poke(path, data, offset):
    """Overwrite raw bytes, as a fault or a misbehaving writer would."""
    with open(path, "r+b") as fh:
        fh.seek(offset)
        fh.write(data)


def test_c1_init(path):
    assert os.path.getsize(path) == 10 * SLOT
    assert lines(path) == [None] * 10


def test_c2_init_refuses_existing_path(path):
    sj.write(path, 0, {"a": 1})
    with pytest.raises(FileExistsError):
        sj.init(path, 3)
    assert os.path.getsize(path) == 10 * SLOT and sj.read(path) == {
        0: {"a": 1}
    }


def test_c3_write_keeps_the_file_plain_jsonl(path):
    record = {"text": "line\nbreak\ttab é ✓", "value": 42}
    sj.write(path, 3, record)
    parsed = lines(path)
    assert parsed[3]["i"] == 3 and parsed[3]["r"] == record
    assert [x for i, x in enumerate(parsed) if i != 3] == [None] * 9
    assert sj.read(path) == {3: record}


def test_c4_rewrite_replaces(path):
    sj.write(path, 3, {"v": 1})
    sj.write(path, 3, {"v": 2}, clear_first=True)
    assert sj.read(path) == {3: {"v": 2}}


def test_c5_torn_first_write_is_missing(path):
    sj.write(path, 2, {"v": 2})
    sj.write(path, 4, {"v": 4})
    poke(path, sj.encode_slot(3, {"v": "x" * 100})[:40], 3 * SLOT)
    assert sj.read(path) == {2: {"v": 2}, 4: {"v": 4}}


def test_c6_mixed_envelopes_fail_the_digest(path):
    sj.write(path, 3, {"v": "aaaaaaaaaa"})
    new = sj.encode_slot(3, {"v": "bbbbbbbbbb"})
    poke(path, new[:14], 3 * SLOT)  # part of the new digest over the old
    assert isinstance(lines(path)[3], dict)  # it still parses
    assert sj.missing(path, 10) == list(range(10))


def test_c7_misplaced_envelope_is_missing(path):
    poke(path, sj.encode_slot(1, {"v": 1}), 7 * SLOT)
    assert 7 in sj.missing(path, 10)


def test_c8_zero_bytes_are_missing(path):
    sj.write(path, 2, {"v": 2})
    sj.write(path, 4, {"v": 4})
    poke(path, b"\0" * SLOT, 3 * SLOT)
    assert sj.read(path) == {2: {"v": 2}, 4: {"v": 4}}


@pytest.mark.parametrize(
    "record,error",
    [
        ({"v": "x" * SLOT}, sj.SlotError),
        ([1, 2], TypeError),
        ({"v": float("nan")}, ValueError),
    ],
)
def test_c9_bad_records_write_nothing(path, record, error):
    with pytest.raises(error):
        sj.write(path, 3, record)
    assert sj.read(path) == {}


def test_c10_never_writes_past_the_end(path):
    with pytest.raises(sj.SlotError):
        sj.write(path, 10, {"v": 1}, wait=0)
    assert os.path.getsize(path) == 10 * SLOT


def test_c11_extend_repairs_and_never_shrinks(path):
    with open(path, "ab") as fh:
        fh.write(b'{"h":"torn')  # a crashed extension's partial slot
    for n_new in (12, 12, 5):
        sj.extend(path, n_new)
        assert os.path.getsize(path) == 12 * SLOT
        assert lines(path) == [None] * 12


def test_c12_c13_concurrent_writers_and_convert(tmp_path):
    path = str(tmp_path / "big.slots.jsonl")
    sj.init(path, 200)
    with ThreadPoolExecutor(32) as pool:
        first = [pool.submit(sj.write, path, i, {"i": i}) for i in range(200)]
        extending = pool.submit(sj.extend, path, 400)  # among the writers
        extending.result()
        rest = [
            pool.submit(sj.write, path, i, {"i": i}) for i in range(200, 400)
        ]
        for future in first + rest:
            future.result()
    assert sj.missing(path, 400) == []
    assert sj.read(path) == {i: {"i": i} for i in range(400)}

    out = str(tmp_path / "plain.jsonl")
    sj.convert(path, out)
    with open(out) as fh:
        assert fh.read() == "".join(f'{{"i":{i}}}\n' for i in range(400))
    sj.convert(path, out, with_index=True)
    assert lines(out)[17] == {"i": 17, "r": {"i": 17}}


def test_c14_slot_size_must_be_whole_pages(tmp_path):
    with pytest.raises(ValueError):
        sj.init(str(tmp_path / "x.slots.jsonl"), 3, slot_bytes=1000)
    assert not os.path.exists(tmp_path / "x.slots.jsonl")


SLOTTED = {
    "how_read_payload": "scd.record.slottedjsonl.read_payload()",
    "how_write_payload": "scd.record.slottedjsonl.write_payload()",
    "how_prep_payload": "scd.record.slottedjsonl.prep_payload()",
}


def test_trials_recorded_in_their_task_id_slots(tmp_path):
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 5, "cmd": 'echo "!!!screendoor:result $((i * i))"'},
        workdir=str(tmp_path),
        **SLOTTED,
    )
    assert r["closed"]["outcome"] == "succeeded"
    assert [t["task_id"] for t in r["trials"]] == [0, 1, 2, 3, 4]
    (ctx,) = load_dispatches(str(tmp_path))
    slots = sj.read(os.path.join(ctx.run_dir, "payload.slots.jsonl"))
    assert sorted(slots) == [0, 1, 2, 3, 4]  # line i is task i's result
    for t in r["trials"]:
        slot_bytes = slots[t["task_id"]]
        assert slot_bytes["event"] == "completed"
        assert slot_bytes["trial_uuid"] == t["trial_uuid"]
        assert slot_bytes["result"] == t["result"] == t["key"]["i"] ** 2
        assert slot_bytes["dispatch_uuid"] == r["dispatch_uuid"]
    appended = read_jsonl_tolerant(os.path.join(ctx.run_dir, "payload.jsonl"))
    assert {e["event"] for e in appended} == {"requested", "launched"}


def test_oversized_trial_record_falls_back_to_appending(tmp_path, caplog):
    big = "x" * sj.DEFAULT_SLOT
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 1},
        fake_trial=lambda t: big,
        workdir=str(tmp_path),
        **SLOTTED,
    )
    assert r["trials"][0]["result"] == big
    assert "goes to payload.jsonl" in caplog.text


def test_jsonl_records_take_no_slots(tmp_path):
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise", {"n": 2}, workdir=str(tmp_path)
    )
    assert [t["task_id"] for t in r["trials"]] == [0, 1]
    assert not list(tmp_path.rglob("*.slots.jsonl"))


def test_slot_size_set_once_in_prep_payload(tmp_path, caplog):
    big = "x" * 6000  # too large for 4096-byte slots, fits in 8192
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 2},
        fake_trial=lambda t: big,
        workdir=str(tmp_path),
        **{**SLOTTED, "how_prep_payload": SLOTTED_8K},
    )
    assert [t["result"] for t in r["trials"]] == [big, big]
    assert "goes to payload.jsonl" not in caplog.text
    (ctx,) = load_dispatches(str(tmp_path))
    path = os.path.join(ctx.run_dir, "payload.slots.jsonl")
    assert os.path.getsize(path) == 2 * 8192
    assert sorted(sj.read(path, None, 8192)) == [0, 1]


SLOTTED_8K = "scd.record.slottedjsonl.prep_payload(slot_bytes=8192)"


def test_mismatched_slot_size_raises(tmp_path):
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 1},
        fake_trial=lambda t: 1,
        workdir=str(tmp_path),
        **{**SLOTTED, "how_prep_payload": SLOTTED_8K},
    )
    (ctx,) = load_dispatches(str(tmp_path))
    with pytest.raises(ValueError, match="8192-byte slots, not 4096"):
        sj.read_payload(slot_bytes=4096)(ctx)
    assert sj.read_payload(slot_bytes=8192)(ctx) == r["trials"]

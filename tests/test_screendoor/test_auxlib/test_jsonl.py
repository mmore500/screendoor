import datetime
import json
import os

import pytest

from screendoor.auxlib._append_jsonl_line import append_jsonl_line
from screendoor.auxlib._canonical_json import canonical_json
from screendoor.auxlib._read_jsonl_tolerant import (
    SchemaTooNewError,
    read_jsonl_tolerant,
)


def test_append_and_read(tmp_path):
    p = str(tmp_path / "x.jsonl")
    append_jsonl_line(p, {"event": "a", "n": 1})
    append_jsonl_line(p, {"event": "b", "n": 2})
    recs = read_jsonl_tolerant(p)
    assert [r["event"] for r in recs] == ["a", "b"]
    for r in recs:
        assert r["schema"] == 1
        assert datetime.datetime.fromisoformat(r["ts"]).tzinfo is not None


def test_torn_lines_skipped(tmp_path, caplog):
    p = str(tmp_path / "x.jsonl")
    append_jsonl_line(p, {"event": "a", "n": 1})
    with open(p, "ab") as fh:  # a spliced fragment, then a later good line
        fh.write(b'{"schema": 1, "event": "b", "n"\n')
        fh.write(b"\x00\x00garbage\n")
    append_jsonl_line(p, {"event": "c", "n": 3})
    assert [r["event"] for r in read_jsonl_tolerant(p)] == ["a", "c"]
    assert "torn" in caplog.text


def test_schema_too_new(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(json.dumps({"schema": 99, "event": "x"}) + "\n")
    with pytest.raises(SchemaTooNewError):
        read_jsonl_tolerant(str(p))


def test_missing_file(tmp_path):
    assert read_jsonl_tolerant(str(tmp_path / "nope.jsonl")) == []


def test_canonical_json_sorted():
    obj = {"b": 1, "a": [1, {"d": 0, "c": 0}]}
    assert canonical_json(obj) == '{"a":[1,{"c":0,"d":0}],"b":1}'


def test_single_write_per_line(tmp_path, monkeypatch):
    calls = []
    real = os.write
    monkeypatch.setattr(
        os, "write", lambda fd, b: calls.append(b) or real(fd, b)
    )
    append_jsonl_line(
        str(tmp_path / "x.jsonl"), {"event": "a", "payload": "x" * 10000}
    )
    assert len(calls) == 1 and calls[0].endswith(b"\n")

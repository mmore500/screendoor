import datetime as dt

from screendoor.notify import pushover
from screendoor.notify.pushover import _send


class Ctx:
    dispatch_uuid = "abcdef12-0000"


NOW = dt.datetime(2026, 11, 11, 12, tzinfo=dt.timezone.utc)


def h(event, minutes_ago, **kw):
    return {
        "event": event,
        "ts": (NOW - dt.timedelta(minutes=minutes_ago)).isoformat(),
        **kw,
    }


def test_no_credentials(monkeypatch):
    monkeypatch.delenv("PUSHOVER_USER", raising=False)
    (ev,) = pushover.notify_immediate()(Ctx(), "failure", "m", {}, [], NOW)
    assert ev["event"] == "suppressed"


def test_send_and_failure(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    sent = []
    monkeypatch.setattr(_send, "_post", lambda url, body: sent.append(body))
    (ev,) = pushover.notify_immediate()(Ctx(), "failure", "m", {}, [], NOW)
    assert ev["event"] == "sent" and b"priority=1" in sent[0]

    def boom(url, body):
        raise OSError("down")

    monkeypatch.setattr(_send, "_post", boom)
    n = pushover.notify_immediate()
    (ev,) = n(Ctx(), "failure", "m2", {}, [], NOW)
    assert ev["event"] == "send_failed"
    monkeypatch.setattr(_send, "_post", lambda url, body: sent.append(body))
    retried = n.flush(
        Ctx(), "failure", [h("send_failed", 1, message="m2")], NOW
    )
    assert [r["event"] for r in retried] == ["sent"]


def test_intermittent(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    monkeypatch.setattr(_send, "_post", lambda url, body: None)
    n = pushover.notify_intermittent(interval_s=3600)
    (ev,) = n(Ctx(), "progress", "1/4", {}, [h("sent", 10)], NOW)
    assert ev["event"] == "suppressed"
    (ev,) = n(Ctx(), "progress", "2/4", {}, [h("sent", 61)], NOW)
    assert ev["event"] == "sent"


def test_batched(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    bodies = []
    monkeypatch.setattr(_send, "_post", lambda url, body: bodies.append(body))
    n = pushover.notify_batched(interval_s=3600)
    (q,) = n(Ctx(), "warning", "disk", {"dedupe_key": "disk"}, [], NOW)
    assert q["event"] == "queued"
    hist = [
        h("queued", 30, message="disk", dedupe_key="disk"),
        h("queued", 20, message="disk", dedupe_key="disk"),
        h("queued", 10, message="other", dedupe_key="o"),
    ]
    (ev,) = n.flush(Ctx(), "warning", hist, NOW)
    assert ev["event"] == "sent" and ev["digest"]
    assert b"x2" in bodies[0]
    hist.append({**ev, "ts": NOW.isoformat()})
    assert n.flush(Ctx(), "warning", hist, NOW) == []

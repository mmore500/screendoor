import datetime as dt

from screendoor.notify import pushover
from screendoor.notify.pushover import _send

CTX = {"dispatch_uuid": "abcdef12-0000"}


NOW = dt.datetime(2026, 11, 11, 12, tzinfo=dt.timezone.utc)


def h(event, minutes_ago, **kw):
    return {
        "event": event,
        "ts": (NOW - dt.timedelta(minutes=minutes_ago)).isoformat(),
        **kw,
    }


def test_no_credentials(monkeypatch):
    monkeypatch.delenv("PUSHOVER_USER", raising=False)
    (ev,) = pushover.notify_immediate()(CTX, "failure", "m", {}, [], NOW)
    assert ev["event"] == "suppressed"


def test_send_and_failure(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    sent = []
    monkeypatch.setattr(_send, "_post", lambda url, body: sent.append(body))
    (ev,) = pushover.notify_immediate()(CTX, "failure", "m", {}, [], NOW)
    assert ev["event"] == "sent" and b"priority=1" in sent[0]

    def boom(url, body):
        raise OSError("down")

    monkeypatch.setattr(_send, "_post", boom)
    n = pushover.notify_immediate()
    (ev,) = n(CTX, "failure", "m2", {}, [], NOW)
    assert ev["event"] == "send_failed"
    monkeypatch.setattr(_send, "_post", lambda url, body: sent.append(body))
    retried = n.flush(CTX, "failure", [h("send_failed", 1, message="m2")], NOW)
    assert [r["event"] for r in retried] == ["sent"]


def test_intermittent(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    monkeypatch.setattr(_send, "_post", lambda url, body: None)
    n = pushover.notify_intermittent(interval_s=3600)
    (ev,) = n(CTX, "progress", "1/4", {}, [h("sent", 10)], NOW)
    assert ev["event"] == "suppressed"
    (ev,) = n(CTX, "progress", "2/4", {}, [h("sent", 61)], NOW)
    assert ev["event"] == "sent"


def test_batched(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    bodies = []
    monkeypatch.setattr(_send, "_post", lambda url, body: bodies.append(body))
    n = pushover.notify_batched(interval_s=3600)
    (q,) = n(CTX, "warning", "disk", {"dedupe_key": "disk"}, [], NOW)
    assert q["event"] == "queued"
    hist = [
        h("queued", 30, message="disk", dedupe_key="disk"),
        h("queued", 20, message="disk", dedupe_key="disk"),
        h("queued", 10, message="other", dedupe_key="o"),
    ]
    (ev,) = n.flush(CTX, "warning", hist, NOW)
    assert ev["event"] == "sent" and ev["digest"]
    assert b"x2" in bodies[0]
    hist.append({**ev, "ts": NOW.isoformat()})
    assert n.flush(CTX, "warning", hist, NOW) == []


def test_batched_resends_what_a_failed_digest_held(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER", "u")
    monkeypatch.setenv("PUSHOVER_TOKEN", "t")
    bodies = []
    monkeypatch.setattr(_send, "_post", lambda url, body: bodies.append(body))
    n = pushover.notify_batched(interval_s=3600)
    hist = [
        h("queued", 200, message="early", dedupe_key="e"),
        h("send_failed", 150, message="early", digest=True),
        h("queued", 100, message="later", dedupe_key="l"),
    ]
    (ev,) = n.flush(CTX, "warning", hist, NOW)
    assert ev["event"] == "sent"
    assert b"early" in bodies[0] and b"later" in bodies[0]

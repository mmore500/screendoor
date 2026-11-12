import logging
import os
import urllib.parse
import urllib.request

API = "https://api.pushover.net/1/messages.json"
PRIORITY = {
    "failure": 1,
    "success": 0,
    "anomaly": 0,
    "termination": 0,
}  # the rest: -1


def _post(url: str, body: bytes) -> None:
    """POST ``body``; tests replace this."""
    urllib.request.urlopen(url, data=body, timeout=20).close()


def send(ctx, level: str, message: str) -> dict:
    """Send one Pushover message; return the notify event describing it."""
    user = os.environ.get("PUSHOVER_USER")
    token = os.environ.get("PUSHOVER_TOKEN")
    if not user or not token:
        logging.warning(
            "screendoor: PUSHOVER_USER or PUSHOVER_TOKEN unset; "
            "not sending %s notification",
            level,
        )
        return {
            "event": "suppressed",
            "reason": "no_credentials",
            "message": message,
        }
    body = urllib.parse.urlencode(
        {
            "user": user,
            "token": token,
            "title": f"screendoor {level} {ctx.dispatch_uuid[:8]}",
            "message": message[:1024],
            "priority": PRIORITY.get(level, -1),
        }
    )
    try:
        _post(API, body.encode())
    except Exception as e:  # recorded; flush retries it on a later tick
        return {
            "event": "send_failed",
            "error": repr(e)[:300],
            "message": message,
        }
    return {"event": "sent", "via": "pushover", "message": message}

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
    """POST `body` to `url`; tests replace this."""
    urllib.request.urlopen(url, data=body, timeout=20).close()


def send(ctx: dict, level: str, message: str) -> dict:
    """Send one Pushover message.

    Parameters
    ----------
    ctx : dict
        The hook context of the dispatch, or of the daemon, the message is
        from.
    level : str
        The notification level, which sets the message's priority.
    message : str
        The text, truncated to 1024 characters.

    Returns
    -------
    dict
        A `sent` or `send_failed` event, or a `suppressed` one if
        `$PUSHOVER_USER` or `$PUSHOVER_TOKEN` is unset.
    """
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
    label = ctx.get("dispatch_uuid", "daemon")
    body = urllib.parse.urlencode(
        {
            "user": user,
            "token": token,
            "title": f"screendoor {level} {label[:8]}",
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

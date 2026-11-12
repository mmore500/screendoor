from ._send import send


def flush():
    """Retry up to three messages whose sends failed."""

    def flush(ctx, level, history, now) -> list:
        sent = {h.get("message") for h in history if h["event"] == "sent"}
        failed = dict.fromkeys(
            h["message"]
            for h in history
            if h["event"] == "send_failed" and h["message"] not in sent
        )
        return [send(ctx, level, message) for message in list(failed)[-3:]]

    return flush

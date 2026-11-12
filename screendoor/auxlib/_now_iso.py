import datetime
import time

# screendoor.testing.FakeClock swaps these in, so tests run in fake time
_clock: dict = {"now": None, "sleep": None}


def now() -> datetime.datetime:
    """Current local time, timezone-aware."""
    if _clock["now"] is not None:
        return _clock["now"]()
    return datetime.datetime.now().astimezone()


def sleep(seconds: float) -> None:
    if _clock["sleep"] is not None:
        return _clock["sleep"](seconds)
    time.sleep(max(0.0, seconds))


def now_iso() -> str:
    """Current time in UTC as ISO-8601, to the microsecond, so that record
    timestamps sort as strings."""
    utc = now().astimezone(datetime.timezone.utc)
    return utc.isoformat(timespec="microseconds")


def parse_iso(ts: str) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.astimezone()

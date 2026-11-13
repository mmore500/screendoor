import datetime
import time

# screendoor.testing.FakeClock swaps these in to run screendoor in fake time
_clock: dict = {"now": None, "sleep": None}


def now() -> datetime.datetime:
    """Return the current local time, timezone-aware.

    Returns
    -------
    datetime.datetime
        The current time, or the installed FakeClock's.
    """
    if _clock["now"] is not None:
        return _clock["now"]()
    return datetime.datetime.now().astimezone()


def sleep(seconds: float) -> None:
    """Sleep for `seconds`, or advance the installed FakeClock by as much.

    Parameters
    ----------
    seconds : float
        How long to sleep; a negative value counts as zero.
    """
    if _clock["sleep"] is not None:
        return _clock["sleep"](seconds)
    time.sleep(max(0.0, seconds))


def now_iso() -> str:
    """Return the current time in UTC as an ISO-8601 timestamp.

    Timestamps carry microseconds, so that record timestamps sort correctly
    as strings.

    Returns
    -------
    str
        The timestamp, such as `2026-01-02T03:04:05.000006+00:00`.
    """
    utc = now().astimezone(datetime.timezone.utc)
    return utc.isoformat(timespec="microseconds")


def parse_iso(ts: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp, such as one from `now_iso`.

    Parameters
    ----------
    ts : str
        The timestamp; one without a timezone is taken as local time.

    Returns
    -------
    datetime.datetime
        The time, timezone-aware.
    """
    dt = datetime.datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.astimezone()

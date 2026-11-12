import datetime
import time

# screendoor.testing.FakeClock swaps these in, so tests run in fake time
_clock: dict = {"now": None, "sleep": None}


def now() -> datetime.datetime:
    """Current local time, timezone-aware.

    Returns
    -------
    datetime.datetime
        The time, or the FakeClock's while one is installed.
    """
    if _clock["now"] is not None:
        return _clock["now"]()
    return datetime.datetime.now().astimezone()


def sleep(seconds: float) -> None:
    """Sleep ``seconds``, or advance the FakeClock while one is installed.

    Parameters
    ----------
    seconds : float
        How long; negative counts as zero.
    """
    if _clock["sleep"] is not None:
        return _clock["sleep"](seconds)
    time.sleep(max(0.0, seconds))


def now_iso() -> str:
    """Current time in UTC as ISO-8601, to the microsecond, so that record
    timestamps sort as strings.

    Returns
    -------
    str
        The timestamp, e.g. ``2026-01-02T03:04:05.000006+00:00``.
    """
    utc = now().astimezone(datetime.timezone.utc)
    return utc.isoformat(timespec="microseconds")


def parse_iso(ts: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp, such as from now_iso.

    Parameters
    ----------
    ts : str
        The timestamp; without a timezone, it is taken as local time.

    Returns
    -------
    datetime.datetime
        The time, timezone-aware.
    """
    dt = datetime.datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.astimezone()

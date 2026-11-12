from __future__ import annotations

import datetime

from ..auxlib import _now_iso


class FakeClock:
    """Fake time, as a context manager: ``sleep`` advances ``now`` at once.

    Parameters
    ----------
    start : datetime.datetime or None, default None
        The time to start at; 2026-11-11 09:00 UTC if None.
    tick_s : float, default 0.001
        Seconds each ``now()`` advances the clock, so timestamps stay
        ordered.
    """

    def __init__(
        self, start: datetime.datetime | None = None, tick_s: float = 0.001
    ) -> None:
        self.t = start or datetime.datetime(
            2026, 11, 11, 9, tzinfo=datetime.timezone.utc
        )
        self.tick_s = tick_s  # now() advances this much, so ts stay ordered
        self._saved = None

    def now(self) -> datetime.datetime:
        """Advance the clock by ``tick_s`` and return the time.

        Returns
        -------
        datetime.datetime
            The time, advanced.
        """
        self.t += datetime.timedelta(seconds=self.tick_s)
        return self.t

    def sleep(self, seconds: float) -> None:
        """Advance the clock by ``seconds`` at once.

        Parameters
        ----------
        seconds : float
            How long to sleep; a negative value counts as 0.
        """
        self.t += datetime.timedelta(seconds=max(0.0, seconds))

    @property
    def active(self) -> bool:
        """Whether the clock is entered, so screendoor runs in fake time."""
        return self._saved is not None

    def __enter__(self) -> FakeClock:
        self._saved = dict(_now_iso._clock)
        _now_iso._clock.update(now=self.now, sleep=self.sleep)
        return self

    def __exit__(self, *exc: object) -> None:
        _now_iso._clock.update(self._saved)
        self._saved = None

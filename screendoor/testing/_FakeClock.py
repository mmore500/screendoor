import datetime

from ..auxlib import _now_iso


class FakeClock:
    """Fake time, as a context manager: ``sleep`` advances ``now`` at once."""

    def __init__(
        self, start: datetime.datetime | None = None, tick_s: float = 0.001
    ):
        self.t = start or datetime.datetime(
            2026, 11, 11, 9, tzinfo=datetime.timezone.utc
        )
        self.tick_s = tick_s  # now() advances this much, so ts stay ordered
        self._saved = None

    def now(self) -> datetime.datetime:
        self.t += datetime.timedelta(seconds=self.tick_s)
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += datetime.timedelta(seconds=max(0.0, seconds))

    def __enter__(self):
        self._saved = dict(_now_iso._clock)
        _now_iso._clock.update(now=self.now, sleep=self.sleep)
        return self

    def __exit__(self, *exc):
        _now_iso._clock.update(self._saved)
        self._saved = None

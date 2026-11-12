import datetime as dt

import pytest

from screendoor.auxlib._next_cron_firing import next_cron_firing

UTC = dt.timezone.utc


def t(*a):
    return dt.datetime(*a, tzinfo=UTC)


@pytest.mark.parametrize(
    "expr,after,want",
    [
        ("*/5 * * * *", t(2026, 11, 11, 9, 2), t(2026, 11, 11, 9, 5)),
        ("*/5 * * * *", t(2026, 11, 11, 9, 5), t(2026, 11, 11, 9, 10)),
        ("* * * * *", t(2026, 11, 11, 9, 5, 30), t(2026, 11, 11, 9, 6)),
        ("0 3 * * *", t(2026, 11, 11, 9, 0), t(2026, 11, 12, 3, 0)),
        ("15,45 8-9 * * *", t(2026, 11, 11, 9, 50), t(2026, 11, 12, 8, 15)),
        ("0 0 1 * *", t(2026, 11, 11), t(2026, 12, 1)),
        ("0 12 * * 0", t(2026, 11, 11), t(2026, 11, 15, 12)),  # Sunday
        ("0 12 * * 7", t(2026, 11, 11), t(2026, 11, 15, 12)),
        ("0 0 29 2 *", t(2026, 3, 1), t(2028, 2, 29)),
        # dom OR dow when both restricted
        ("0 0 13 * 5", t(2026, 11, 11), t(2026, 11, 13)),
        ("10-20/5 * * * *", t(2026, 11, 11, 9, 16), t(2026, 11, 11, 9, 20)),
    ],
)
def test_firings(expr, after, want):
    assert next_cron_firing(expr, after) == want


@pytest.mark.parametrize(
    "bad", ["* * * *", "61 * * * *", "*/0 * * * *", "a * * * *"]
)
def test_bad(bad):
    with pytest.raises(ValueError):
        next_cron_firing(bad, t(2026, 1, 1))

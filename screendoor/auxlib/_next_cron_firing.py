import datetime

_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _parse_field(text: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError(f"bad cron step in {text!r}")
        if part == "*":
            start, stop = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, stop = int(a), int(b)
        else:
            start = int(part)
            stop = hi if step != 1 else start
        if not (lo <= start <= hi and lo <= stop <= hi and start <= stop):
            raise ValueError(f"cron field {text!r} out of range {lo}-{hi}")
        values.update(range(start, stop + 1, step))
    return values


def parse_cron(
    expr: str,
) -> tuple[set[int], set[int], set[int], set[int], set[int], bool, bool]:
    """Parse a five-field cron expression.

    Parameters
    ----------
    expr : str
        Minute, hour, day of month, month and day of week.

    Returns
    -------
    tuple
        ``(minute, hour, dom, month, dow, dom_star, dow_star)``: the values
        each field allows (Sunday is day 0), and whether day of month and
        day of week are ``*``.

    Raises
    ------
    ValueError
        If ``expr`` is not five valid fields.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron expression needs five fields: {expr!r}")
    minute, hour, dom, month, dow = (
        _parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, _RANGES)
    )
    dow = {d % 7 for d in dow}  # 7 == Sunday
    return minute, hour, dom, month, dow, fields[2] == "*", fields[4] == "*"


def next_cron_firing(
    expr: str,
    after: datetime.datetime,
) -> datetime.datetime:
    """First firing of five-field cron ``expr`` strictly after ``after``.

    Supports lists, ranges and steps. As in Vixie cron, when both day of
    month and day of week are restricted, either may match.

    Parameters
    ----------
    expr : str
        Minute, hour, day of month, month and day of week.
    after : datetime.datetime
        The time to search from.

    Returns
    -------
    datetime.datetime
        The firing, in ``after``'s timezone.

    Raises
    ------
    ValueError
        If ``expr`` is invalid or never fires.
    """
    minute, hour, dom, month, dow, dom_star, dow_star = parse_cron(expr)
    tz = after.tzinfo
    t = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    day = t.date()
    for _ in range(366 * 8):  # enough for any valid expression incl. Feb 29
        if day.month in month:
            dom_ok = day.day in dom
            dow_ok = (day.isoweekday() % 7) in dow
            if dom_star or dow_star:
                ok = dom_ok and dow_ok
            else:
                ok = dom_ok or dow_ok
            if ok:
                for h in sorted(hour):
                    for m in sorted(minute):
                        cand = datetime.datetime(
                            day.year,
                            day.month,
                            day.day,
                            h,
                            m,
                            tzinfo=tz,
                        )
                        if cand >= t:
                            return cand
        day += datetime.timedelta(days=1)
        t = datetime.datetime(day.year, day.month, day.day, tzinfo=tz)
    raise ValueError(f"cron expression never fires: {expr!r}")

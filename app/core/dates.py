"""Date helpers shared by the calculation engine."""
import datetime

ISO = "%Y-%m-%d"


def parse(value):
    """Accept a date, datetime, ISO string, or None.  Returns date or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text:
        text = text.split(" ", 1)[0]
    return datetime.datetime.strptime(text, ISO).date()


def fmt(value):
    value = parse(value)
    return value.isoformat() if value else None


def year_end(year, month=12, day=31):
    """Financial year end for a given year, tolerant of short months."""
    if month == 12 and day == 31:
        return datetime.date(year, 12, 31)
    try:
        return datetime.date(year, month, day)
    except ValueError:
        # e.g. 31 February -> last valid day of that month
        next_month = datetime.date(year + (month // 12), (month % 12) + 1, 1)
        return next_month - datetime.timedelta(days=1)
    

def year_start(year, month=12, day=31):
    """First day of the financial year that ends on year_end(year)."""
    return year_end(year - 1, month, day) + datetime.timedelta(days=1)


def add_days(value, count):
    return parse(value) + datetime.timedelta(days=count)


def overlap_days(a_start, a_end, b_start, b_end):
    """Inclusive day count of the intersection of two date ranges."""
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return 0
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end < start:
        return 0
    return (end - start).days + 1

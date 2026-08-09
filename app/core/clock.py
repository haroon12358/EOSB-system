"""Current-date resolution.

On start-up the application tries to obtain the date from the internet.  If
no connection is available it silently falls back to the computer's local
system date.  The result is cached for the life of the process and refreshed
lazily once a day so a long-running session still rolls over at midnight.
"""
import datetime
import email.utils
import threading

from . import config

_TIME_SOURCES = (
    "https://www.google.com",
    "https://www.cloudflare.com",
    "https://www.microsoft.com",
)

_lock = threading.Lock()
_state = {"date": None, "source": None, "checked_local": None}


def _fetch_online_date(timeout):
    """Read the Date header of a well known host.  Returns a date or None."""
    import urllib.request

    for url in _TIME_SOURCES:
        try:
            request = urllib.request.Request(url, method="HEAD")
            request.add_header("User-Agent", "EOSB/1.0")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                header = response.headers.get("Date")
            if not header:
                continue
            parsed = email.utils.parsedate_to_datetime(header)
            if parsed is None:
                continue
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            return parsed.date()
        except Exception:
            continue
    return None


def today(force_refresh=False):
    """Return today's date, preferring an online source."""
    local_today = datetime.date.today()
    with _lock:
        if (
            not force_refresh
            and _state["date"] is not None
            and _state["checked_local"] == local_today
        ):
            return _state["date"]

    resolved, source = local_today, "system"
    if config.get("use_online_date", True):
        online = _fetch_online_date(float(config.get("online_date_timeout", 2.0)))
        if online is not None:
            resolved, source = online, "online"

    with _lock:
        _state["date"] = resolved
        _state["source"] = source
        _state["checked_local"] = local_today
    return resolved


def source():
    if _state["source"] is None:
        today()
    return _state["source"]


def info():
    value = today()
    return {
        "today": value.isoformat(),
        "source": _state["source"],
        "system_date": datetime.date.today().isoformat(),
    }

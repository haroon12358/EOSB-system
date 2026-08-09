"""Application configuration and path resolution.

Every path is derived from the location of this file, so the application
always uses the database that lives inside its own folder.  Moving or
copying the folder moves the data with it.
"""
import json
import os
import sys
import threading

# app/core/config.py -> app/core -> app -> <APPLICATION ROOT>
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(CORE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)

WEB_DIR = os.path.join(APP_DIR, "web")
DATA_DIR = os.path.join(ROOT_DIR, "data")
CONFIG_DIR = os.path.join(ROOT_DIR, "config")
BACKUP_DIR = os.path.join(ROOT_DIR, "backups")
LOG_DIR = os.path.join(ROOT_DIR, "logs")

DB_PATH = os.path.join(DATA_DIR, "eosb.db")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")

APP_NAME = "EOSB Management System"
APP_VERSION = "1.0.0"

for _d in (DATA_DIR, CONFIG_DIR, BACKUP_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# Defaults.  These mirror the accounting assumptions found in the source
# workbook.  They are configurable so that a change in labour law never
# requires a change in code.
# ---------------------------------------------------------------------------
DEFAULTS = {
    "organisation_name": "Corbild Investments Establishment",
    "currency": "SAR",
    "currency_symbol": "SAR",

    # Entitlement formula parameters (Saudi Labour Law, Article 84)
    "first_period_days": 1825,      # 5 years expressed in days, as per workbook
    "days_per_year": 365,           # divisor converting service days to years
    "first_period_factor": 0.5,     # half a month's wage per year, first 5 years
    "later_period_factor": 1.0,     # one month's wage per year thereafter
    "rounding_decimals": 1,         # workbook rounds entitlement to 1 decimal

    # Service day counting.  The workbook uses an inclusive count
    # (year end - joining date + 1).
    "inclusive_service_days": True,

    # Article 85 scaling on resignation.  Applied to the amount legally
    # payable at settlement, never to the carried provision.
    "apply_resignation_scale": True,

    # Financial year end (month/day).  Supports non-calendar year ends.
    "year_end_month": 12,
    "year_end_day": 31,

    # Date resolution
    "use_online_date": True,
    "online_date_timeout": 2.0,

    # Server
    "preferred_port": 8731,
    "open_browser": True,
}

_lock = threading.Lock()
_cache = None


def _read_file():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def load():
    """Return the effective settings (defaults overlaid with saved values)."""
    global _cache
    with _lock:
        if _cache is None:
            merged = dict(DEFAULTS)
            merged.update(_read_file())
            _cache = merged
        return dict(_cache)


def get(key, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def save(updates):
    """Persist setting changes immediately and refresh the cache."""
    global _cache
    with _lock:
        current = dict(DEFAULTS)
        current.update(_read_file())
        for key, value in updates.items():
            if key in DEFAULTS:
                current[key] = value
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_PATH)
        _cache = current
        return dict(current)


def reset():
    global _cache
    with _lock:
        _cache = None

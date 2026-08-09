"""SQLite persistence layer.

The database file lives inside the application folder.  Every write is
committed immediately, so there is never an unsaved state.
"""
import datetime
import os
import sqlite3
import threading

from . import config

_local = threading.local()

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_no        TEXT,
    identity_number    TEXT,
    name               TEXT NOT NULL,
    joining_date       TEXT NOT NULL,
    termination_date   TEXT,
    termination_reason TEXT,
    status             TEXT NOT NULL DEFAULT 'Active',
    department         TEXT,
    position           TEXT,
    notes              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS salary_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    effective_date  TEXT NOT NULL,
    previous_salary REAL,
    new_salary      REAL NOT NULL,
    reason          TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_salary_emp ON salary_history(employee_id, effective_date);

CREATE TABLE IF NOT EXISTS unpaid_leave (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    days        INTEGER NOT NULL,
    reason      TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_leave_emp ON unpaid_leave(employee_id, start_date);

CREATE TABLE IF NOT EXISTS benefits_paid (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id  INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    payment_date TEXT NOT NULL,
    amount       REAL NOT NULL,
    reference    TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_paid_emp ON benefits_paid(employee_id, payment_date);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect():
    """Thread-local connection to the database inside the application folder."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # A single-file journal (rather than WAL) keeps the database to one
        # file, so the application folder can be copied or moved safely and
        # works on network shares and removable drives.
        conn.execute("PRAGMA journal_mode = TRUNCATE")
        conn.execute("PRAGMA synchronous = FULL")
        _local.conn = conn
    return conn


def close():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def query(sql, params=()):
    return [dict(row) for row in connect().execute(sql, params).fetchall()]


def one(sql, params=()):
    row = connect().execute(sql, params).fetchone()
    return dict(row) if row else None


def execute(sql, params=()):
    conn = connect()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor


def log(entity, entity_id, action, detail=""):
    execute(
        "INSERT INTO audit_log (at, entity, entity_id, action, detail) VALUES (?,?,?,?,?)",
        (now(), entity, entity_id, action, detail),
    )


def _quarantine_unreadable_database():
    """Move a damaged database aside so the application can still start."""
    import datetime
    import shutil
    if not os.path.exists(config.DB_PATH):
        return None
    spoiled = os.path.join(
        config.BACKUP_DIR,
        "unreadable_%s.db" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        shutil.move(config.DB_PATH, spoiled)
    except OSError:
        return None
    return spoiled


def initialise():
    """Create the schema if absent and seed the opening employee master.

    A damaged database is moved aside and rebuilt rather than stopping the
    application, and the opening employee master is restored if the tables
    are empty and nothing was ever deleted.
    """
    repaired = None
    try:
        conn = connect()
        conn.executescript(SCHEMA)
        conn.commit()
    except sqlite3.DatabaseError:
        close()
        repaired = _quarantine_unreadable_database()
        conn = connect()
        conn.executescript(SCHEMA)
        conn.commit()

    version = one("SELECT value FROM meta WHERE key='schema_version'")
    if version is None:
        execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),))

    # Seed on first run, and restore the opening master if the file is empty
    # but no employee was ever deliberately deleted.
    empty = one("SELECT COUNT(*) AS c FROM employees")["c"] == 0
    deletions = one("SELECT COUNT(*) AS c FROM audit_log "
                    "WHERE entity='employee' AND action='delete'")["c"]
    if empty and deletions == 0:
        _seed()
        if one("SELECT value FROM meta WHERE key='seeded'") is None:
            execute("INSERT INTO meta (key, value) VALUES ('seeded', ?)", (now(),))

    if repaired:
        log("system", None, "repair", "Unreadable database moved to %s" % repaired)
    return {"repaired": repaired}


def health():
    """A plain description of the state of the database, for diagnostics."""
    import datetime
    info = {"database": config.DB_PATH,
            "exists": os.path.exists(config.DB_PATH),
            "size": os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0,
            "writable": os.access(config.DATA_DIR, os.W_OK),
            "folder": config.ROOT_DIR,
            "checked_at": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        info["integrity"] = connect().execute("PRAGMA integrity_check").fetchone()[0]
        for table in ("employees", "salary_history", "unpaid_leave", "benefits_paid"):
            info[table] = one("SELECT COUNT(*) AS c FROM %s" % table)["c"]
        info["ok"] = info["integrity"] == "ok"
    except Exception as exc:
        info["ok"] = False
        info["error"] = "%s: %s" % (type(exc).__name__, exc)
    return info


# ---------------------------------------------------------------------------
# Opening balances carried over from the source workbook.
# ---------------------------------------------------------------------------
SEED_EMPLOYEES = [
    ("1", "2138652470", "Ahmed Abdullah Abdulrazzaq",     "2023-09-27",  800.0),
    ("2", "2599691512", "Ahmed Abdullah Mahmoud",         "2025-05-27", 4000.0),
    ("3", "1043546686", "Omar Ali Al-Zahrani",            "2025-12-01", 4000.0),
    ("4", "1094825773", "Rayana Ali Al-Zahrani",          "2025-07-13", 5000.0),
    ("5", "2596347621", "Suhail Naseem Mohammed Khalid",  "2025-11-26",  800.0),
]


def _seed():
    stamp = now()
    for employee_no, identity, name, joining, salary in SEED_EMPLOYEES:
        cursor = execute(
            """INSERT INTO employees
               (employee_no, identity_number, name, joining_date, status,
                notes, created_at, updated_at)
               VALUES (?,?,?,?,'Active',?,?,?)""",
            (employee_no, identity, name, joining,
             "Opening record migrated from the provision workbook.", stamp, stamp),
        )
        execute(
            """INSERT INTO salary_history
               (employee_id, effective_date, previous_salary, new_salary, reason, created_at)
               VALUES (?,?,?,?,?,?)""",
            (cursor.lastrowid, joining, None, salary, "Salary on joining", stamp),
        )
    log("system", None, "seed", "Seeded %d employees from workbook" % len(SEED_EMPLOYEES))

"""Backup and restore.

A backup is a single zip file containing the database, the configuration and
a manifest.  It is written to the user's Downloads folder so it is easy to
find and easy to carry to another computer.
"""
import datetime
import json
import os
import shutil
import sqlite3
import zipfile

from . import config, db

MANIFEST = "manifest.json"


def downloads_dir():
    """Locate the current user's Downloads folder on Windows, macOS or Linux."""
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, "Downloads")]
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE")
        if profile:
            candidates.insert(0, os.path.join(profile, "Downloads"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    try:
        os.makedirs(candidates[0], exist_ok=True)
        return candidates[0]
    except OSError:
        return config.BACKUP_DIR


def _counts():
    out = {}
    for table in ("employees", "salary_history", "unpaid_leave", "benefits_paid"):
        try:
            out[table] = db.one("SELECT COUNT(*) AS c FROM %s" % table)["c"]
        except sqlite3.Error:
            out[table] = 0
    return out


def create(destination=None):
    """Write a backup and return its path."""
    db.connect().commit()
    target_dir = destination or downloads_dir()
    os.makedirs(target_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "EOSB_Backup_%s.eosbak" % stamp
    path = os.path.join(target_dir, name)

    # Copy the database through SQLite so the file is always consistent.
    staging = os.path.join(config.BACKUP_DIR, "_staging.db")
    source = db.connect()
    target = sqlite3.connect(staging)
    with target:
        source.backup(target)
    target.close()

    manifest = {
        "application": config.APP_NAME,
        "version": config.APP_VERSION,
        "schema_version": db.SCHEMA_VERSION,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "counts": _counts(),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
        zf.write(staging, "eosb.db")
        if os.path.exists(config.SETTINGS_PATH):
            zf.write(config.SETTINGS_PATH, "settings.json")
    os.remove(staging)

    # Keep a copy inside the application folder as well.
    try:
        shutil.copy2(path, os.path.join(config.BACKUP_DIR, name))
    except OSError:
        pass

    db.log("system", None, "backup", path)
    return {"path": path, "folder": target_dir, "filename": name,
            "manifest": manifest, "size": os.path.getsize(path)}


def inspect(archive_path):
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()
        if "eosb.db" not in names:
            raise ValueError("This file is not a valid EOSB backup.")
        manifest = {}
        if MANIFEST in names:
            manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
    return manifest


def restore(archive_path, keep_settings=False):
    """Replace the current database with the one inside the backup."""
    manifest = inspect(archive_path)

    staging = os.path.join(config.BACKUP_DIR, "_restore.db")
    with zipfile.ZipFile(archive_path, "r") as zf:
        with open(staging, "wb") as fh:
            fh.write(zf.read("eosb.db"))
        settings_blob = zf.read("settings.json") if "settings.json" in zf.namelist() else None

    # Validate before committing to the swap.
    probe = sqlite3.connect(staging)
    try:
        probe.execute("SELECT COUNT(*) FROM employees").fetchone()
    finally:
        probe.close()

    # Keep a safety copy of the database being replaced, then swap.
    db.close()
    if os.path.exists(config.DB_PATH):
        safety = os.path.join(
            config.BACKUP_DIR,
            "pre_restore_%s.db" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(config.DB_PATH, safety)
    shutil.move(staging, config.DB_PATH)

    if settings_blob and not keep_settings:
        with open(config.SETTINGS_PATH, "wb") as fh:
            fh.write(settings_blob)
        config.reset()

    db.initialise()
    db.log("system", None, "restore", archive_path)
    return {"manifest": manifest, "counts": _counts()}

"""JSON API.  Every endpoint writes through to the database immediately."""
import json
import os

from . import backup, clock, config, db, dates, repo, rollforward
from ..reports import builders


class ApiError(Exception):
    def __init__(self, message, status=400):
        Exception.__init__(self, message)
        self.status = status


def _int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError("%s must be a number." % name)


def _require(payload, *fields):
    for field in fields:
        if payload.get(field) in (None, ""):
            raise ApiError("%s is required." % field.replace("_", " ").title())


def _validate_employee(payload, employee_id=None):
    _require(payload, "name", "joining_date")
    try:
        joining = dates.parse(payload["joining_date"])
    except ValueError:
        raise ApiError("Joining date must be a valid date.")
    if joining is None:
        raise ApiError("Joining date is required.")
    termination = None
    if payload.get("termination_date"):
        try:
            termination = dates.parse(payload["termination_date"])
        except ValueError:
            raise ApiError("Termination date must be a valid date.")
        if termination < joining:
            raise ApiError("Termination date cannot precede the joining date.")
    identity = (payload.get("identity_number") or "").strip()
    if identity:
        sql = "SELECT id FROM employees WHERE identity_number = ?"
        params = [identity]
        if employee_id:
            sql += " AND id <> ?"
            params.append(employee_id)
        if db.one(sql, params):
            raise ApiError("Another employee already has identity number %s." % identity)


# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------
def handle(method, path, query, payload):
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts or parts[0] != "api":
        raise ApiError("Not found", 404)
    parts = parts[1:]
    if not parts:
        raise ApiError("Not found", 404)
    section = parts[0]
    rest = parts[1:]

    if section == "meta" and method == "GET":
        settings = config.load()
        return {
            "app": config.APP_NAME, "version": config.APP_VERSION,
            "root": config.ROOT_DIR, "database": config.DB_PATH,
            "settings": settings, "clock": clock.info(),
            "downloads": backup.downloads_dir(),
        }

    if section == "health" and method == "GET":
        report = db.health()
        report["clock"] = clock.info()
        report["app"] = config.APP_NAME
        report["version"] = config.APP_VERSION
        return report

    if section == "reseed" and method == "POST":
        from . import db as _db
        _db._seed()
        return {"employees": len(repo.list_employees())}

    if section == "settings":
        if method == "GET":
            return config.load()
        if method in ("PUT", "POST"):
            saved = config.save(payload or {})
            db.log("settings", None, "update", ", ".join(sorted((payload or {}).keys())))
            return saved
        raise ApiError("Method not allowed", 405)

    if section == "dashboard" and method == "GET":
        return rollforward.dashboard(query.get("as_of"))

    if section == "schedule" and method == "GET":
        return rollforward.build(query.get("as_of"))

    if section == "employees":
        return _employees(method, rest, query, payload)

    if section == "salaries":
        return _salaries(method, rest, query, payload)

    if section == "leave":
        return _leave(method, rest, query, payload)

    if section == "payments":
        return _payments(method, rest, query, payload)

    if section == "reports":
        return _reports(method, rest, query, payload)

    if section == "backup":
        return _backup(method, rest, query, payload)

    if section == "shutdown" and method == "POST":
        import threading
        threading.Timer(0.4, lambda: os._exit(0)).start()
        return {"stopping": True}

    if section == "audit" and method == "GET":
        return {"entries": db.query(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 300")}

    raise ApiError("Not found", 404)


def _employees(method, rest, query, payload):
    if not rest:
        if method == "GET":
            return {"employees": repo.list_employees(query.get("search"),
                                                     query.get("status"))}
        if method == "POST":
            _validate_employee(payload)
            employee = repo.create_employee(payload)
            return {"employee": employee}
        raise ApiError("Method not allowed", 405)

    employee_id = _int(rest[0], "Employee id")
    if len(rest) == 1:
        if method == "GET":
            employee = repo.get_employee(employee_id)
            if not employee:
                raise ApiError("Employee not found.", 404)
            employee["salaries"] = repo.list_salaries(employee_id)
            employee["leave"] = repo.list_leave(employee_id)
            employee["payments"] = repo.list_payments(employee_id)
            employee["current_salary"] = repo.current_salary(employee_id)
            return {"employee": employee}
        if method in ("PUT", "PATCH"):
            existing = repo.get_employee(employee_id)
            if not existing:
                raise ApiError("Employee not found.", 404)
            merged = dict(existing)
            merged.update(payload or {})
            _validate_employee(merged, employee_id)
            return {"employee": repo.update_employee(employee_id, payload or {})}
        if method == "DELETE":
            if not repo.delete_employee(employee_id):
                raise ApiError("Employee not found.", 404)
            return {"deleted": employee_id}
        raise ApiError("Method not allowed", 405)

    raise ApiError("Not found", 404)


def _salaries(method, rest, query, payload):
    if method == "GET":
        employee_id = query.get("employee_id")
        return {"salaries": repo.list_salaries(int(employee_id) if employee_id else None)}
    if method == "POST":
        payload = payload or {}
        _require(payload, "employee_id", "effective_date", "new_salary")
        if not repo.get_employee(int(payload["employee_id"])):
            raise ApiError("Employee not found.", 404)
        try:
            amount = float(payload["new_salary"])
        except (TypeError, ValueError):
            raise ApiError("New salary must be a number.")
        if amount < 0:
            raise ApiError("Salary cannot be negative.")
        return {"salaries": repo.add_salary(
            int(payload["employee_id"]), payload["effective_date"], amount,
            payload.get("reason"))}
    if method == "DELETE" and rest:
        try:
            repo.delete_salary(_int(rest[0], "Record id"))
        except ValueError as exc:
            raise ApiError(str(exc))
        return {"deleted": rest[0]}
    raise ApiError("Method not allowed", 405)


def _leave(method, rest, query, payload):
    if method == "GET":
        employee_id = query.get("employee_id")
        return {"leave": repo.list_leave(int(employee_id) if employee_id else None)}
    if method == "POST":
        payload = payload or {}
        _require(payload, "employee_id", "start_date")
        return {"leave": repo.add_leave(
            int(payload["employee_id"]), payload["start_date"],
            payload.get("end_date") or payload["start_date"], payload.get("reason"))}
    if method == "DELETE" and rest:
        repo.delete_leave(_int(rest[0], "Record id"))
        return {"deleted": rest[0]}
    raise ApiError("Method not allowed", 405)


def _payments(method, rest, query, payload):
    if method == "GET":
        employee_id = query.get("employee_id")
        return {"payments": repo.list_payments(int(employee_id) if employee_id else None)}
    if method == "POST":
        payload = payload or {}
        _require(payload, "employee_id", "payment_date", "amount")
        try:
            amount = float(payload["amount"])
        except (TypeError, ValueError):
            raise ApiError("Amount must be a number.")
        return {"payments": repo.add_payment(
            int(payload["employee_id"]), payload["payment_date"], amount,
            payload.get("reference"), payload.get("notes"))}
    if method == "DELETE" and rest:
        repo.delete_payment(_int(rest[0], "Record id"))
        return {"deleted": rest[0]}
    raise ApiError("Method not allowed", 405)


def _reports(method, rest, query, payload):
    if method == "GET" and not rest:
        return {"reports": builders.REPORTS}
    if method == "POST":
        payload = payload or {}
        kind = payload.get("kind")
        fmt = payload.get("format", "xlsx")
        if kind not in builders.REPORTS:
            raise ApiError("Unknown report type.")
        if fmt not in ("xlsx", "pdf"):
            raise ApiError("Format must be xlsx or pdf.")
        out_dir = payload.get("folder") or backup.downloads_dir()
        try:
            path = builders.generate(
                kind, fmt, out_dir, payload.get("as_of"),
                int(payload["employee_id"]) if payload.get("employee_id") else None,
                int(payload["year"]) if payload.get("year") else None)
        except ValueError as exc:
            raise ApiError(str(exc))
        db.log("report", None, "generate", os.path.basename(path))
        return {"path": path, "folder": os.path.dirname(path),
                "filename": os.path.basename(path),
                "size": os.path.getsize(path)}
    raise ApiError("Method not allowed", 405)


def _backup(method, rest, query, payload):
    action = rest[0] if rest else ""
    if method == "POST" and action == "create":
        return backup.create((payload or {}).get("folder"))
    if method == "POST" and action == "restore":
        path = (payload or {}).get("path")
        if not path:
            raise ApiError("Select a backup file to restore.")
        if not os.path.exists(path):
            raise ApiError("That backup file could not be found:\n%s" % path)
        try:
            return backup.restore(path)
        except Exception as exc:
            raise ApiError("Restore failed: %s" % exc)
    if method == "GET" and action == "list":
        folder = config.BACKUP_DIR
        entries = []
        for name in sorted(os.listdir(folder), reverse=True):
            if name.endswith(".eosbak"):
                full = os.path.join(folder, name)
                entries.append({"filename": name, "path": full,
                                "size": os.path.getsize(full)})
        return {"backups": entries, "folder": folder,
                "downloads": backup.downloads_dir()}
    raise ApiError("Not found", 404)

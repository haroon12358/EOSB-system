"""Data access.  Every write commits immediately - there is no save button."""
from . import db, dates


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
EMPLOYEE_FIELDS = (
    "employee_no", "identity_number", "name", "joining_date", "termination_date",
    "termination_reason", "status", "department", "position", "notes",
)


def _derive_status(payload):
    """Status is derived from the termination date, never contradicting it.

    In the source workbook the status column was decorative: no calculation
    read it, so an employee marked Terminated with no date kept accruing.
    """
    return "Terminated" if dates.parse(payload.get("termination_date")) else "Active"


def list_employees(search=None, status=None):
    sql = "SELECT * FROM employees WHERE 1=1"
    params = []
    if search:
        sql += " AND (name LIKE ? OR identity_number LIKE ? OR employee_no LIKE ?)"
        like = "%%%s%%" % search
        params += [like, like, like]
    if status in ("Active", "Terminated"):
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY CAST(employee_no AS INTEGER), name"
    return db.query(sql, params)


def get_employee(employee_id):
    return db.one("SELECT * FROM employees WHERE id = ?", (employee_id,))


def create_employee(payload):
    stamp = db.now()
    payload = dict(payload)
    payload["status"] = _derive_status(payload)
    if not payload.get("employee_no"):
        top = db.one("SELECT MAX(CAST(employee_no AS INTEGER)) AS m FROM employees")
        payload["employee_no"] = str((top["m"] or 0) + 1)
    columns = ", ".join(EMPLOYEE_FIELDS)
    marks = ", ".join("?" for _ in EMPLOYEE_FIELDS)
    values = [payload.get(f) for f in EMPLOYEE_FIELDS]
    cursor = db.execute(
        "INSERT INTO employees (%s, created_at, updated_at) VALUES (%s, ?, ?)"
        % (columns, marks),
        values + [stamp, stamp],
    )
    employee_id = cursor.lastrowid
    salary = payload.get("monthly_salary")
    if salary not in (None, ""):
        add_salary(employee_id, payload.get("joining_date"), float(salary),
                   "Salary on joining")
    db.log("employee", employee_id, "create", payload.get("name", ""))
    return get_employee(employee_id)


def update_employee(employee_id, payload):
    existing = get_employee(employee_id)
    if not existing:
        return None
    merged = dict(existing)
    for field in EMPLOYEE_FIELDS:
        if field in payload:
            merged[field] = payload[field]
    merged["status"] = _derive_status(merged)
    sets = ", ".join("%s = ?" % f for f in EMPLOYEE_FIELDS)
    db.execute(
        "UPDATE employees SET %s, updated_at = ? WHERE id = ?" % sets,
        [merged.get(f) for f in EMPLOYEE_FIELDS] + [db.now(), employee_id],
    )
    db.log("employee", employee_id, "update", merged.get("name", ""))
    return get_employee(employee_id)


def delete_employee(employee_id):
    existing = get_employee(employee_id)
    if not existing:
        return False
    db.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    db.log("employee", employee_id, "delete", existing.get("name", ""))
    return True


# ---------------------------------------------------------------------------
# Salary history - salary is never overwritten
# ---------------------------------------------------------------------------
def list_salaries(employee_id=None):
    if employee_id:
        return db.query(
            "SELECT * FROM salary_history WHERE employee_id = ? "
            "ORDER BY effective_date, id", (employee_id,))
    return db.query(
        "SELECT s.*, e.name AS employee_name FROM salary_history s "
        "JOIN employees e ON e.id = s.employee_id "
        "ORDER BY s.effective_date DESC, s.id DESC")


def current_salary(employee_id, on_date=None):
    from . import engine
    records = list_salaries(employee_id)
    if not records:
        return 0.0
    if on_date is None:
        return float(records[-1]["new_salary"])
    return engine.salary_at(records, on_date)


def add_salary(employee_id, effective_date, new_salary, reason=None):
    records = list_salaries(employee_id)
    previous = None
    if records:
        from . import engine
        previous = engine.salary_at(records, effective_date)
    db.execute(
        """INSERT INTO salary_history
           (employee_id, effective_date, previous_salary, new_salary, reason, created_at)
           VALUES (?,?,?,?,?,?)""",
        (employee_id, dates.fmt(effective_date), previous, float(new_salary),
         reason, db.now()),
    )
    db.log("salary", employee_id, "add", "%s -> %s on %s"
           % (previous, new_salary, dates.fmt(effective_date)))
    return list_salaries(employee_id)


def delete_salary(record_id):
    row = db.one("SELECT * FROM salary_history WHERE id = ?", (record_id,))
    if not row:
        return False
    remaining = db.one(
        "SELECT COUNT(*) AS c FROM salary_history WHERE employee_id = ?",
        (row["employee_id"],))
    if remaining["c"] <= 1:
        raise ValueError("An employee must keep at least one salary record.")
    db.execute("DELETE FROM salary_history WHERE id = ?", (record_id,))
    db.log("salary", row["employee_id"], "delete", str(record_id))
    return True


# ---------------------------------------------------------------------------
# Unpaid leave
# ---------------------------------------------------------------------------
def list_leave(employee_id=None):
    if employee_id:
        return db.query(
            "SELECT * FROM unpaid_leave WHERE employee_id = ? ORDER BY start_date",
            (employee_id,))
    return db.query(
        "SELECT l.*, e.name AS employee_name FROM unpaid_leave l "
        "JOIN employees e ON e.id = l.employee_id ORDER BY l.start_date DESC")


def add_leave(employee_id, start_date, end_date, reason=None):
    start = dates.parse(start_date)
    end = dates.parse(end_date) or start
    if end < start:
        start, end = end, start
    days = (end - start).days + 1
    db.execute(
        """INSERT INTO unpaid_leave
           (employee_id, start_date, end_date, days, reason, created_at)
           VALUES (?,?,?,?,?,?)""",
        (employee_id, start.isoformat(), end.isoformat(), days, reason, db.now()),
    )
    db.log("leave", employee_id, "add", "%s..%s (%d days)" % (start, end, days))
    return list_leave(employee_id)


def delete_leave(record_id):
    row = db.one("SELECT * FROM unpaid_leave WHERE id = ?", (record_id,))
    if not row:
        return False
    db.execute("DELETE FROM unpaid_leave WHERE id = ?", (record_id,))
    db.log("leave", row["employee_id"], "delete", str(record_id))
    return True


# ---------------------------------------------------------------------------
# Benefits paid
# ---------------------------------------------------------------------------
def list_payments(employee_id=None):
    if employee_id:
        return db.query(
            "SELECT * FROM benefits_paid WHERE employee_id = ? ORDER BY payment_date",
            (employee_id,))
    return db.query(
        "SELECT p.*, e.name AS employee_name FROM benefits_paid p "
        "JOIN employees e ON e.id = p.employee_id ORDER BY p.payment_date DESC")


def add_payment(employee_id, payment_date, amount, reference=None, notes=None):
    db.execute(
        """INSERT INTO benefits_paid
           (employee_id, payment_date, amount, reference, notes, created_at)
           VALUES (?,?,?,?,?,?)""",
        (employee_id, dates.fmt(payment_date), float(amount), reference, notes,
         db.now()),
    )
    db.log("payment", employee_id, "add", "%s on %s" % (amount, dates.fmt(payment_date)))
    return list_payments(employee_id)


def delete_payment(record_id):
    row = db.one("SELECT * FROM benefits_paid WHERE id = ?", (record_id,))
    if not row:
        return False
    db.execute("DELETE FROM benefits_paid WHERE id = ?", (record_id,))
    db.log("payment", row["employee_id"], "delete", str(record_id))
    return True


# ---------------------------------------------------------------------------
# Bulk load for the calculation engine
# ---------------------------------------------------------------------------
def load_all():
    """Load everything the engine needs in four queries rather than 4N."""
    employees = db.query("SELECT * FROM employees ORDER BY CAST(employee_no AS INTEGER), name")
    salaries, leave, payments = {}, {}, {}
    for row in db.query("SELECT * FROM salary_history ORDER BY effective_date, id"):
        salaries.setdefault(row["employee_id"], []).append(row)
    for row in db.query("SELECT * FROM unpaid_leave ORDER BY start_date"):
        leave.setdefault(row["employee_id"], []).append(row)
    for row in db.query("SELECT * FROM benefits_paid ORDER BY payment_date"):
        payments.setdefault(row["employee_id"], []).append(row)
    return employees, salaries, leave, payments

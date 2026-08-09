"""Report generation: Employee EOS, Provision Schedule, Roll Forward, Statement."""
import datetime
import os

from ..core import clock, config, dates, engine, repo, rollforward
from . import pdf, xlsx

SCHEDULE_COLUMNS = [
    ("employee_no", "No", 5, "c", "text"),
    ("name", "Employee Name", 26, "l", "text"),
    ("calculation_date", "Calculation Date", 12, "c", "date"),
    ("salary", "Monthly Salary", 11, "r", "money"),
    ("service_days", "Service Days at Year End", 10, "r", "int"),
    ("leave_first", "Unpaid Leave First 5 Yrs", 10, "r", "int"),
    ("leave_later", "Unpaid Leave After 5 Yrs", 10, "r", "int"),
    ("days_first", "Days in First 5 Years", 10, "r", "int"),
    ("days_later", "Days Over 5 Years", 10, "r", "int"),
    ("net_service_days", "Net Service Days", 10, "r", "int"),
    ("entitlement", "Entitlement at Year End", 12, "r", "num"),
    ("opening_provision", "Opening Provision", 12, "r", "num"),
    ("charge_for_year", "Charge for the Year", 12, "r", "num"),
    ("benefits_paid", "Benefits Paid During Year", 12, "r", "num"),
    ("closing_provision", "Closing Provision", 12, "r", "num"),
]

STYLE_FOR = {
    "text": xlsx.S_TEXT, "date": xlsx.S_DATE, "int": xlsx.S_INT,
    "num": xlsx.S_NUM1, "money": xlsx.S_MONEY,
}
TOTAL_STYLE_FOR = {
    "text": xlsx.S_TOTAL_TEXT, "date": xlsx.S_TOTAL_TEXT, "int": xlsx.S_TOTAL_INT,
    "num": xlsx.S_TOTAL_NUM, "money": xlsx.S_TOTAL_NUM,
}


def _fmt(value, kind):
    if value is None or value == "":
        return ""
    if kind == "int":
        return "{:,.0f}".format(float(value))
    if kind == "num":
        return "{:,.1f}".format(float(value))
    if kind == "money":
        return "{:,.2f}".format(float(value))
    return str(value)


def _cell(value, kind):
    if value in (None, ""):
        return None
    if kind == "date":
        return dates.parse(value)
    if kind in ("int", "num", "money"):
        return float(value)
    return str(value)


def _stamp(settings):
    return "Generated %s  |  %s  |  Amounts in %s" % (
        datetime.datetime.now().strftime("%d %b %Y %H:%M"),
        settings.get("organisation_name", ""), settings.get("currency", "SAR"))


def _slug(text):
    keep = [c if c.isalnum() or c in "-_" else "_" for c in str(text)]
    return "".join(keep).strip("_")[:60] or "report"


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def _write_block(sheet, block, settings, heading):
    sheet.add([heading], xlsx.S_SUBTITLE)
    sheet.add([c[1] for c in SCHEDULE_COLUMNS], xlsx.S_HEADER)
    for row in block["rows"]:
        sheet.add([_cell(row.get(key), kind) for key, _, _, _, kind in SCHEDULE_COLUMNS],
                  styles=[STYLE_FOR[kind] for _, _, _, _, kind in SCHEDULE_COLUMNS])
    totals = block["totals"]
    total_row, total_styles = [], []
    for index, (key, _, _, _, kind) in enumerate(SCHEDULE_COLUMNS):
        if index == 0:
            total_row.append("Total"); total_styles.append(xlsx.S_TOTAL_TEXT)
        elif key in totals and kind != "money":
            total_row.append(float(totals[key])); total_styles.append(TOTAL_STYLE_FOR[kind])
        else:
            total_row.append(None); total_styles.append(xlsx.S_TOTAL_TEXT)
    sheet.add(total_row, styles=total_styles)
    sheet.blank()


def _titles(sheet, settings, title, subtitle):
    sheet.add([settings.get("organisation_name", "")], xlsx.S_TITLE)
    sheet.add([title], xlsx.S_SUBTITLE)
    sheet.add([subtitle], xlsx.S_SUBTITLE)
    sheet.blank()


def schedule_xlsx(path, schedule, settings, single_year=None):
    widths = [c[2] for c in SCHEDULE_COLUMNS]
    wb = xlsx.Workbook()
    blocks = schedule["blocks"]
    if single_year is not None:
        blocks = [b for b in blocks if b["year"] == single_year]
    title = ("Provision Schedule" if single_year is not None
             else "End of Service Benefits - Provision Roll Forward")
    sheet = wb.sheet("Provision Schedule", freeze_row=6, widths=widths)
    _titles(sheet, settings, title,
            "Reporting date %s  |  Amounts in %s"
            % (schedule["as_of"], settings.get("currency", "SAR")))
    for block in blocks:
        _write_block(sheet, block, settings, "Year Ended %s" % block["year_end"])

    if single_year is None and len(blocks) > 1:
        summary = wb.sheet("Movement Summary", freeze_row=5,
                           widths=[12, 16, 16, 16, 16, 16])
        _titles(summary, settings, "Provision Movement by Year", "All reporting years")
        summary.add(["Year", "Opening Provision", "Charge for the Year",
                     "Benefits Paid", "Closing Provision", "Total Entitlement"],
                    xlsx.S_HEADER)
        for block in blocks:
            t = block["totals"]
            summary.add([block["year"], t["opening_provision"], t["charge_for_year"],
                         t["benefits_paid"], t["closing_provision"], t["entitlement"]],
                        styles=[xlsx.S_INT] + [xlsx.S_NUM1] * 5)
    return wb.save(path)


def employees_xlsx(path, schedule, settings):
    block = rollforward.current_block(schedule)
    widths = [6, 16, 28, 12, 12, 12, 13, 11, 11, 12, 13, 13]
    wb = xlsx.Workbook()
    sheet = wb.sheet("Employee EOS", freeze_row=6, widths=widths)
    _titles(sheet, settings, "Employee End of Service Report",
            "Position at %s  |  Amounts in %s"
            % (block["year_end"], settings.get("currency", "SAR")))
    sheet.add(["No", "Identity Number", "Employee Name", "Joining Date",
               "Termination Date", "Status", "Monthly Salary", "Service Days",
               "Net Service Days", "Service Years", "Entitlement",
               "Closing Provision"], xlsx.S_HEADER)
    styles = [xlsx.S_TEXT, xlsx.S_TEXT, xlsx.S_TEXT, xlsx.S_DATE, xlsx.S_DATE,
              xlsx.S_TEXT, xlsx.S_MONEY, xlsx.S_INT, xlsx.S_INT, xlsx.S_NUM1,
              xlsx.S_NUM1, xlsx.S_NUM1]
    for row in block["rows"]:
        sheet.add([row["employee_no"], row["identity_number"], row["name"],
                   _cell(row["joining_date"], "date"),
                   _cell(row["termination_date"], "date"), row["status"],
                   row["salary"], row["service_days"], row["net_service_days"],
                   row["service_years"], row["entitlement"],
                   row["closing_provision"]], styles=styles)
    t = block["totals"]
    sheet.add(["Total", None, None, None, None, None, None, t["service_days"],
               t["net_service_days"], None, t["entitlement"], t["closing_provision"]],
              styles=[xlsx.S_TOTAL_TEXT] * 7 + [xlsx.S_TOTAL_INT, xlsx.S_TOTAL_INT,
                                                xlsx.S_TOTAL_TEXT, xlsx.S_TOTAL_NUM,
                                                xlsx.S_TOTAL_NUM])
    return wb.save(path)


def statement_xlsx(path, employee_id, schedule, settings):
    employee = repo.get_employee(employee_id)
    wb = xlsx.Workbook()
    sheet = wb.sheet("Statement", widths=[26, 16, 16, 16, 16, 16, 16])
    _titles(sheet, settings, "Employee End of Service Statement", employee["name"])
    for label, value in (
        ("Employee Number", employee.get("employee_no")),
        ("Identity Number", employee.get("identity_number")),
        ("Joining Date", employee.get("joining_date")),
        ("Termination Date", employee.get("termination_date") or "-"),
        ("Status", employee.get("status")),
        ("Notes", employee.get("notes") or "-"),
    ):
        sheet.add([label, value], styles=[xlsx.S_TOTAL_TEXT, xlsx.S_TEXT])
    sheet.blank()

    sheet.add(["Provision Movement by Year"], xlsx.S_SUBTITLE)
    sheet.add(["Year", "Calculation Date", "Salary", "Net Service Days",
               "Entitlement", "Opening", "Charge", "Paid", "Closing"], xlsx.S_HEADER)
    for block in schedule["blocks"]:
        for row in block["rows"]:
            if row["employee_id"] != employee_id:
                continue
            sheet.add([block["year"], _cell(row["calculation_date"], "date"),
                       row["salary"], row["net_service_days"], row["entitlement"],
                       row["opening_provision"], row["charge_for_year"],
                       row["benefits_paid"], row["closing_provision"]],
                      styles=[xlsx.S_INT, xlsx.S_DATE, xlsx.S_MONEY, xlsx.S_INT] +
                             [xlsx.S_NUM1] * 5)
    sheet.blank()

    sheet.add(["Salary History"], xlsx.S_SUBTITLE)
    sheet.add(["Effective Date", "Previous Salary", "New Salary", "Reason"], xlsx.S_HEADER)
    for record in repo.list_salaries(employee_id):
        sheet.add([_cell(record["effective_date"], "date"), record["previous_salary"],
                   record["new_salary"], record["reason"]],
                  styles=[xlsx.S_DATE, xlsx.S_MONEY, xlsx.S_MONEY, xlsx.S_TEXT])
    sheet.blank()

    leave = repo.list_leave(employee_id)
    sheet.add(["Unpaid Leave"], xlsx.S_SUBTITLE)
    sheet.add(["From", "To", "Days", "Reason"], xlsx.S_HEADER)
    for record in leave or []:
        sheet.add([_cell(record["start_date"], "date"), _cell(record["end_date"], "date"),
                   record["days"], record["reason"]],
                  styles=[xlsx.S_DATE, xlsx.S_DATE, xlsx.S_INT, xlsx.S_TEXT])
    if not leave:
        sheet.add(["None recorded"], xlsx.S_TEXT)
    sheet.blank()

    payments = repo.list_payments(employee_id)
    sheet.add(["Benefits Paid"], xlsx.S_SUBTITLE)
    sheet.add(["Payment Date", "Amount", "Reference", "Notes"], xlsx.S_HEADER)
    for record in payments or []:
        sheet.add([_cell(record["payment_date"], "date"), record["amount"],
                   record["reference"], record["notes"]],
                  styles=[xlsx.S_DATE, xlsx.S_MONEY, xlsx.S_TEXT, xlsx.S_TEXT])
    if not payments:
        sheet.add(["None recorded"], xlsx.S_TEXT)
    return wb.save(path)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
# The schedule carries fifteen columns; the printed report uses shorter
# headings so that nothing is truncated on a landscape page.
PDF_LABELS = {
    "name": "Employee Name", "calculation_date": "Calc Date", "salary": "Salary",
    "service_days": "Service Days", "leave_first": "Lv 1-5y",
    "leave_later": "Lv 5y+", "days_first": "Days 1-5y", "days_later": "Days 5y+",
    "net_service_days": "Net Days", "entitlement": "Entitlement",
    "opening_provision": "Opening", "charge_for_year": "Charge",
    "benefits_paid": "Paid", "closing_provision": "Closing",
}
PDF_WIDTHS = {
    "name": 24, "calculation_date": 11, "salary": 10, "service_days": 13,
    "leave_first": 9, "leave_later": 9, "days_first": 9, "days_later": 9,
    "net_service_days": 9, "entitlement": 11, "opening_provision": 10,
    "charge_for_year": 10, "benefits_paid": 9, "closing_provision": 11,
}


def _pdf_block(doc, block, settings):
    keys = [c for c in SCHEDULE_COLUMNS if c[0] != "employee_no"]
    columns = [PDF_LABELS[c[0]] for c in keys]
    widths = [PDF_WIDTHS[c[0]] for c in keys]
    aligns = [c[3] for c in keys]
    fields = [(c[0], c[4]) for c in keys]
    rows = [[_fmt(row.get(key), kind) for key, kind in fields] for row in block["rows"]]
    totals = ["Total"] + [
        _fmt(block["totals"].get(key), kind) if key in block["totals"] and kind != "money" else ""
        for key, kind in fields[1:]
    ]
    doc.heading("Year Ended %s" % block["year_end"])
    doc.table(pdf.Table(columns, widths, aligns, rows, totals))


def schedule_pdf(path, schedule, settings, single_year=None):
    blocks = schedule["blocks"]
    if single_year is not None:
        blocks = [b for b in blocks if b["year"] == single_year]
    title = ("Provision Schedule" if single_year is not None
             else "End of Service Benefits - Provision Roll Forward")
    doc = pdf.Document(True, title, settings.get("organisation_name", ""),
                       "Reporting date %s" % schedule["as_of"], _stamp(settings))
    for block in blocks:
        _pdf_block(doc, block, settings)
    return doc.save(path)


def employees_pdf(path, schedule, settings):
    block = rollforward.current_block(schedule)
    doc = pdf.Document(True, "Employee End of Service Report",
                       settings.get("organisation_name", ""),
                       "Position at %s" % block["year_end"], _stamp(settings))
    t = block["totals"]
    doc.key_values([
        ("Employees", t["headcount"]), ("Active", t["active"]),
        ("Terminated", t["terminated"]),
        ("Total Entitlement", _fmt(t["entitlement"], "num")),
        ("Closing Provision", _fmt(t["closing_provision"], "num")),
    ], columns=5)
    doc.spacer(4)
    columns = ["Employee Name", "Identity", "Joining", "Termination", "Status",
               "Salary", "Service Days", "Net Days", "Years", "Entitlement", "Closing"]
    rows = [[r["name"], r["identity_number"] or "", r["joining_date"] or "",
             r["termination_date"] or "-", r["status"], _fmt(r["salary"], "money"),
             _fmt(r["service_days"], "int"), _fmt(r["net_service_days"], "int"),
             "{:.2f}".format(r["service_years"]), _fmt(r["entitlement"], "num"),
             _fmt(r["closing_provision"], "num")] for r in block["rows"]]
    totals = ["Total", "", "", "", "", "", _fmt(t["service_days"], "int"),
              _fmt(t["net_service_days"], "int"), "", _fmt(t["entitlement"], "num"),
              _fmt(t["closing_provision"], "num")]
    doc.table(pdf.Table(columns, [24, 13, 11, 11, 9, 11, 11, 10, 8, 12, 12],
                        ["l", "l", "c", "c", "c", "r", "r", "r", "r", "r", "r"],
                        rows, totals))
    return doc.save(path)


def statement_pdf(path, employee_id, schedule, settings):
    employee = repo.get_employee(employee_id)
    doc = pdf.Document(False, "Employee End of Service Statement",
                       settings.get("organisation_name", ""), employee["name"],
                       _stamp(settings))
    doc.key_values([
        ("Employee Number", employee.get("employee_no") or "-"),
        ("Identity Number", employee.get("identity_number") or "-"),
        ("Status", employee.get("status")),
        ("Joining Date", employee.get("joining_date")),
        ("Termination Date", employee.get("termination_date") or "-"),
        ("Reason", employee.get("termination_reason") or "-"),
    ], columns=3)
    doc.spacer(6)

    doc.heading("Provision Movement by Year", 9.5)
    rows = []
    for block in schedule["blocks"]:
        for row in block["rows"]:
            if row["employee_id"] == employee_id:
                rows.append([block["year"], row["calculation_date"],
                             _fmt(row["salary"], "money"),
                             _fmt(row["net_service_days"], "int"),
                             _fmt(row["entitlement"], "num"),
                             _fmt(row["opening_provision"], "num"),
                             _fmt(row["charge_for_year"], "num"),
                             _fmt(row["benefits_paid"], "num"),
                             _fmt(row["closing_provision"], "num")])
    doc.table(pdf.Table(["Year", "Calc Date", "Salary", "Net Days", "Entitlement",
                         "Opening", "Charge", "Paid", "Closing"],
                        [8, 13, 12, 10, 13, 12, 12, 11, 13],
                        ["c", "c", "r", "r", "r", "r", "r", "r", "r"], rows))

    doc.heading("Salary History", 9.5)
    salary_rows = [[r["effective_date"], _fmt(r["previous_salary"], "money") or "-",
                    _fmt(r["new_salary"], "money"), r["reason"] or ""]
                   for r in repo.list_salaries(employee_id)]
    doc.table(pdf.Table(["Effective Date", "Previous Salary", "New Salary", "Reason"],
                        [16, 16, 16, 38], ["c", "r", "r", "l"], salary_rows))

    doc.heading("Unpaid Leave", 9.5)
    leave_rows = [[r["start_date"], r["end_date"], _fmt(r["days"], "int"), r["reason"] or ""]
                  for r in repo.list_leave(employee_id)] or [["-", "-", "0", "None recorded"]]
    doc.table(pdf.Table(["From", "To", "Days", "Reason"], [16, 16, 10, 44],
                        ["c", "c", "r", "l"], leave_rows))

    doc.heading("Benefits Paid", 9.5)
    payment_rows = [[r["payment_date"], _fmt(r["amount"], "money"), r["reference"] or "",
                     r["notes"] or ""] for r in repo.list_payments(employee_id)] \
                   or [["-", "0.00", "", "None recorded"]]
    doc.table(pdf.Table(["Payment Date", "Amount", "Reference", "Notes"],
                        [16, 14, 20, 36], ["c", "r", "l", "l"], payment_rows))
    return doc.save(path)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
REPORTS = {
    "employees": "Employee EOS Report",
    "schedule": "Provision Schedule",
    "rollforward": "Roll Forward Report",
    "statement": "Employee Statement",
}


def generate(kind, fmt, out_dir, as_of=None, employee_id=None, year=None):
    settings = config.load()
    schedule = rollforward.build(as_of, settings)
    os.makedirs(out_dir, exist_ok=True)
    tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if kind == "statement":
        if not employee_id:
            raise ValueError("An employee must be selected for a statement.")
        employee = repo.get_employee(employee_id)
        if not employee:
            raise ValueError("Employee not found.")
        name = "Employee_Statement_%s_%s" % (_slug(employee["name"]), tag)
    else:
        name = "%s_%s" % (_slug(REPORTS.get(kind, kind).replace(" ", "_")), tag)

    path = os.path.join(out_dir, "%s.%s" % (name, "xlsx" if fmt == "xlsx" else "pdf"))

    if kind == "employees":
        (employees_xlsx if fmt == "xlsx" else employees_pdf)(path, schedule, settings)
    elif kind == "schedule":
        target = year if year is not None else rollforward.current_block(schedule)["year"]
        (schedule_xlsx if fmt == "xlsx" else schedule_pdf)(path, schedule, settings, target)
    elif kind == "rollforward":
        (schedule_xlsx if fmt == "xlsx" else schedule_pdf)(path, schedule, settings, None)
    elif kind == "statement":
        (statement_xlsx if fmt == "xlsx" else statement_pdf)(path, employee_id, schedule, settings)
    else:
        raise ValueError("Unknown report: %s" % kind)
    return path

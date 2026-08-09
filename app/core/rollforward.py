"""Provision roll-forward.

Builds one block per financial year, starting at the year the first employee
joined and running through to the current reporting year.  Nothing is
hardcoded: when a new year begins the schedule simply grows by one block, so
the application never needs updating to keep working.

Roll-forward identity used here:

    Closing Provision = Opening Provision + Charge for the Year - Benefits Paid
    Charge for the Year = Closing Provision - Opening Provision + Benefits Paid

The workbook instead defined the charge as the year-on-year change in
entitlement and let the closing balance fall out.  That works only while no
benefit is ever paid to a serving employee; the moment one is, the carried
provision drifts permanently below the measured liability.  Here the closing
balance is anchored to the measured obligation and the charge is the
balancing figure, which is what the accounting standard expects.  With no
benefits paid the two methods give identical numbers, so the workbook's
comparatives are unaffected.  The workbook's figure is still reported as
``charge_excel_method`` so the two can be reconciled.
"""
from . import clock, config, dates, engine, repo


def _payments_upto(payments, upto):
    upto = dates.parse(upto)
    return round(sum(
        float(p["amount"]) for p in payments
        if dates.parse(p["payment_date"]) is not None
        and dates.parse(p["payment_date"]) <= upto
    ), 2)


def _payments_between(payments, start, end):
    start, end = dates.parse(start), dates.parse(end)
    return round(sum(
        float(p["amount"]) for p in payments
        if dates.parse(p["payment_date"]) is not None
        and start <= dates.parse(p["payment_date"]) <= end
    ), 2)


def year_range(employees, as_of, settings):
    """Every financial year that needs to be reported."""
    month = int(settings.get("year_end_month", 12))
    day = int(settings.get("year_end_day", 31))
    joining_years = [
        dates.parse(e["joining_date"]).year
        for e in employees if e.get("joining_date")
    ]
    as_of = dates.parse(as_of)
    if not joining_years:
        return [], month, day

    first = min(joining_years)
    # An employee joining after this year's year end belongs to the next year.
    first_ye = dates.year_end(first, month, day)
    if min(dates.parse(e["joining_date"]) for e in employees) > first_ye:
        first += 1

    last = as_of.year
    if as_of > dates.year_end(last, month, day):
        last += 1
    for employee in employees:
        termination = dates.parse(employee.get("termination_date"))
        if termination and termination.year > last:
            last = termination.year
    return list(range(first, last + 1)), month, day


def build(as_of=None, settings=None):
    """Return the full year-by-year provision schedule."""
    settings = settings or config.load()
    as_of = dates.parse(as_of) if as_of else clock.today()
    employees, salaries, leave, payments = repo.load_all()

    years, month, day = year_range(employees, as_of, settings)
    decimals = int(settings.get("rounding_decimals", 1))

    previous_closing = {}
    previous_entitlement = {}
    blocks = []

    for year in years:
        block_end = dates.year_end(year, month, day)
        block_start = dates.year_start(year, month, day)
        # A future year is never measured beyond today.
        measure_at = min(block_end, as_of) if block_end > as_of else block_end

        rows = []
        for employee in employees:
            employee_id = employee["id"]
            emp_payments = payments.get(employee_id, [])
            m = engine.measure(
                employee, salaries.get(employee_id, []),
                leave.get(employee_id, []), measure_at, settings,
            )

            paid_in_year = _payments_between(emp_payments, block_start, block_end)
            paid_to_date = _payments_upto(emp_payments, block_end)

            # Once an employee has left and been settled the obligation is
            # extinguished; until then it is the amount legally payable.
            if m["has_left"]:
                closing = round(max(m["payable"] - paid_to_date, 0.0), decimals)
            else:
                closing = round(m["entitlement"], decimals)

            opening = round(previous_closing.get(employee_id, 0.0), decimals)
            charge = round(closing - opening + paid_in_year, decimals)
            excel_charge = round(
                m["entitlement"] - previous_entitlement.get(employee_id, 0.0), decimals
            )

            row = dict(m)
            row.update({
                "year": year,
                "year_end": block_end.isoformat(),
                "opening_provision": opening,
                "charge_for_year": charge,
                "benefits_paid": paid_in_year,
                "benefits_paid_to_date": paid_to_date,
                "closing_provision": closing,
                "charge_excel_method": excel_charge,
                "reconciling_difference": round(charge - excel_charge, decimals),
                "employee_no": employee.get("employee_no"),
                "identity_number": employee.get("identity_number"),
                "status": employee.get("status"),
                "is_future": block_end > as_of,
            })
            rows.append(row)

            previous_closing[employee_id] = closing
            previous_entitlement[employee_id] = m["entitlement"]

        blocks.append({
            "year": year,
            "year_start": block_start.isoformat(),
            "year_end": block_end.isoformat(),
            "is_current": block_start <= as_of <= block_end,
            "is_future": block_start > as_of,
            "rows": rows,
            "totals": totals(rows),
        })

    return {
        "as_of": as_of.isoformat(),
        "date_source": clock.source(),
        "years": years,
        "current_year": as_of.year if as_of <= dates.year_end(as_of.year, month, day)
                        else as_of.year + 1,
        "blocks": blocks,
        "currency": settings.get("currency", "SAR"),
        "organisation_name": settings.get("organisation_name", ""),
    }


TOTAL_FIELDS = (
    "service_days", "leave_first", "leave_later", "days_first", "days_later",
    "net_service_days", "entitlement", "opening_provision", "charge_for_year",
    "benefits_paid", "closing_provision", "settlement_adjustment",
)


def totals(rows):
    out = {}
    for field in TOTAL_FIELDS:
        value = sum(float(r.get(field) or 0) for r in rows)
        out[field] = round(value, 2) if isinstance(value, float) else value
    out["headcount"] = len(rows)
    out["active"] = sum(1 for r in rows if not r["has_left"])
    out["terminated"] = sum(1 for r in rows if r["has_left"])
    return out


def current_block(schedule):
    for block in schedule["blocks"]:
        if block["is_current"]:
            return block
    return schedule["blocks"][-1] if schedule["blocks"] else None


def dashboard(as_of=None, settings=None):
    settings = settings or config.load()
    schedule = build(as_of, settings)
    block = current_block(schedule)
    if block is None:
        return {
            "as_of": schedule["as_of"], "reporting_year": None,
            "opening_provision": 0, "charge_for_year": 0, "benefits_paid": 0,
            "closing_provision": 0, "total_entitlement": 0,
            "active_employees": 0, "terminated_employees": 0, "headcount": 0,
            "currency": settings.get("currency", "SAR"),
            "organisation_name": settings.get("organisation_name", ""),
            "date_source": schedule["date_source"], "history": [],
        }
    t = block["totals"]
    return {
        "as_of": schedule["as_of"],
        "date_source": schedule["date_source"],
        "reporting_year": block["year"],
        "year_end": block["year_end"],
        "opening_provision": t["opening_provision"],
        "charge_for_year": t["charge_for_year"],
        "benefits_paid": t["benefits_paid"],
        "closing_provision": t["closing_provision"],
        "total_entitlement": t["entitlement"],
        "active_employees": t["active"],
        "terminated_employees": t["terminated"],
        "headcount": t["headcount"],
        "currency": settings.get("currency", "SAR"),
        "organisation_name": settings.get("organisation_name", ""),
        "history": [
            {"year": b["year"],
             "opening": b["totals"]["opening_provision"],
             "charge": b["totals"]["charge_for_year"],
             "paid": b["totals"]["benefits_paid"],
             "closing": b["totals"]["closing_provision"]}
            for b in schedule["blocks"] if not b["is_future"]
        ],
    }

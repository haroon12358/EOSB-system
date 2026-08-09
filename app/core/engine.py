"""End of Service Benefits calculation engine.

The entitlement formula reproduces the source workbook exactly:

    Entitlement = ROUND( H / 365 * Salary * 0.5  +  I / 365 * Salary , 1 )

where H is the number of service days falling inside the first five years
and I is the number of service days beyond five years, each net of unpaid
leave taken in that band.  This is Article 84 of the Saudi Labour Law:
half a month's wage for each of the first five years, a full month's wage
for each year thereafter.

Every parameter (1825, 365, 0.5, 1.0, rounding) is supplied by settings so
that a change in law never requires a change in code.

This module is pure: it performs no database access and has no side
effects, which makes it directly testable against the workbook.
"""
from . import dates


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------
def salary_at(salary_records, on_date):
    """Salary in force on a given date.

    Records are (effective_date, new_salary).  The latest record effective on
    or before the date wins.  If the date precedes every record, the earliest
    salary is used, which is the salary the employee joined on.
    """
    on_date = dates.parse(on_date)
    if not salary_records or on_date is None:
        return 0.0
    ordered = sorted(salary_records, key=lambda r: dates.parse(r["effective_date"]))
    applicable = [r for r in ordered if dates.parse(r["effective_date"]) <= on_date]
    chosen = applicable[-1] if applicable else ordered[0]
    return float(chosen["new_salary"] or 0.0)


# ---------------------------------------------------------------------------
# Service and unpaid leave
# ---------------------------------------------------------------------------
def measurement_date(joining, termination, as_of):
    """The date the entitlement is measured at.

    Mirrors the workbook: the reporting date for a serving employee, or the
    termination date once the employee has left.
    """
    as_of = dates.parse(as_of)
    termination = dates.parse(termination)
    if termination is None:
        return as_of
    return min(termination, as_of)


def service_days(joining, upto, inclusive=True):
    """Total elapsed service days.  Zero before the employee joins."""
    joining = dates.parse(joining)
    upto = dates.parse(upto)
    if joining is None or upto is None or joining > upto:
        return 0
    return (upto - joining).days + (1 if inclusive else 0)


def leave_split(joining, upto, leave_records, first_period_days):
    """Split unpaid leave into the first-five-year band and the later band.

    The workbook requires the user to classify each leave day by hand.  Here
    the split is derived from the leave dates themselves, which removes a
    source of manual error.

    Service day 1 is the joining date, so the first band spans
    [joining, joining + first_period_days - 1].
    """
    joining = dates.parse(joining)
    upto = dates.parse(upto)
    if joining is None or upto is None or joining > upto:
        return 0, 0

    band_end = dates.add_days(joining, first_period_days - 1)
    first = later = 0
    for record in leave_records or []:
        start = dates.parse(record.get("start_date"))
        end = dates.parse(record.get("end_date")) or start
        if start is None:
            continue
        if end < start:
            start, end = end, start
        # Only leave falling within the measured service period counts.
        first += dates.overlap_days(start, end, joining, min(band_end, upto))
        if upto > band_end:
            later += dates.overlap_days(
                start, end, dates.add_days(band_end, 1), upto
            )
    return first, later


# ---------------------------------------------------------------------------
# Entitlement
# ---------------------------------------------------------------------------
def entitlement(days_first, days_later, salary, settings):
    per_year = float(settings.get("days_per_year", 365))
    f1 = float(settings.get("first_period_factor", 0.5))
    f2 = float(settings.get("later_period_factor", 1.0))
    decimals = int(settings.get("rounding_decimals", 1))
    raw = (days_first / per_year) * salary * f1 + (days_later / per_year) * salary * f2
    return round(raw, decimals)


def resignation_factor(net_days, reason, settings):
    """Article 85 scaling applied to the amount legally payable on leaving.

    Applies only when the employee resigns.  Dismissal, redundancy, end of
    contract, death and disability all attract the full Article 84 award.
    """
    if not settings.get("apply_resignation_scale", True):
        return 1.0
    if (reason or "").strip().lower() != "resignation":
        return 1.0
    years = net_days / float(settings.get("days_per_year", 365))
    if years < 2:
        return 0.0
    if years < 5:
        return 1.0 / 3.0
    if years < 10:
        return 2.0 / 3.0
    return 1.0


# ---------------------------------------------------------------------------
# Full measurement at a point in time
# ---------------------------------------------------------------------------
def measure(employee, salary_records, leave_records, as_of, settings):
    """Measure one employee's position at a reporting date.

    Returns every intermediate figure the workbook shows, so the result can
    be reconciled line by line.
    """
    first_period = int(settings.get("first_period_days", 1825))
    inclusive = bool(settings.get("inclusive_service_days", True))
    decimals = int(settings.get("rounding_decimals", 1))

    joining = dates.parse(employee.get("joining_date"))
    termination = dates.parse(employee.get("termination_date"))
    calc_date = measurement_date(joining, termination, as_of)

    total_days = service_days(joining, calc_date, inclusive)
    leave_first, leave_later = leave_split(
        joining, calc_date, leave_records, first_period
    )

    # Guard against negative bands, which the workbook does not do: heavy
    # unpaid leave could otherwise produce a negative entitlement.
    days_first = max(min(total_days, first_period) - leave_first, 0)
    days_later = max(max(total_days - first_period, 0) - leave_later, 0)
    net_days = days_first + days_later

    salary = salary_at(salary_records, calc_date) if total_days > 0 else salary_at(
        salary_records, joining
    )
    gross = entitlement(days_first, days_later, salary, settings)

    has_left = termination is not None and termination <= dates.parse(as_of)
    factor = (
        resignation_factor(net_days, employee.get("termination_reason"), settings)
        if has_left
        else 1.0
    )
    payable = round(gross * factor, decimals)

    return {
        "employee_id": employee.get("id"),
        "name": employee.get("name"),
        "joining_date": dates.fmt(joining),
        "termination_date": dates.fmt(termination),
        "calculation_date": dates.fmt(calc_date),
        "salary": round(salary, 2),
        "service_days": total_days,
        "leave_first": leave_first,
        "leave_later": leave_later,
        "days_first": days_first,
        "days_later": days_later,
        "net_service_days": net_days,
        "service_years": round(net_days / float(settings.get("days_per_year", 365)), 2),
        "entitlement": gross,
        "settlement_factor": round(factor, 4),
        "payable": payable,
        "settlement_adjustment": round(gross - payable, decimals),
        "has_left": has_left,
    }

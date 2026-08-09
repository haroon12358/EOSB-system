"""Verification suite.

The first group re-implements the workbook's formulas independently and
asserts the engine agrees cell for cell.  The remaining groups cover the
situations the workbook could not handle.
"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def fresh_app():
    """Point the application at a throwaway folder and reload its modules."""
    tmp = tempfile.mkdtemp(prefix="eosb_test_")
    for name in list(sys.modules):
        if name.startswith("app."):
            del sys.modules[name]
    from app.core import config
    config.DATA_DIR = os.path.join(tmp, "data")
    config.CONFIG_DIR = os.path.join(tmp, "config")
    config.BACKUP_DIR = os.path.join(tmp, "backups")
    config.DB_PATH = os.path.join(config.DATA_DIR, "eosb.db")
    config.SETTINGS_PATH = os.path.join(config.CONFIG_DIR, "settings.json")
    config.ROOT_DIR = tmp
    for folder in (config.DATA_DIR, config.CONFIG_DIR, config.BACKUP_DIR):
        os.makedirs(folder, exist_ok=True)
    config.reset()
    from app.core import db
    db.close()
    db.initialise()
    return tmp


# --------------------------------------------------------------------------
# 1. Independent re-implementation of the workbook formulas
# --------------------------------------------------------------------------
WORKBOOK = [
    ("Ahmed Abdullah Abdulrazzaq", datetime.date(2023, 9, 27), 800),
    ("Ahmed Abdullah Mahmoud", datetime.date(2025, 5, 27), 4000),
    ("Omar Ali Al-Zahrani", datetime.date(2025, 12, 1), 4000),
    ("Rayana Ali Al-Zahrani", datetime.date(2025, 7, 13), 5000),
    ("Suhail Naseem Mohammed Khalid", datetime.date(2025, 11, 26), 800),
]


def excel_rows(year_end):
    """Literal transcription of the workbook formulas in columns B..O."""
    out = []
    for name, joining, salary in WORKBOOK:
        b = year_end                                   # B: =IF(F="",YearEnd,MIN(F,YearEnd))
        c = 0 if joining > b else (b - joining).days + 1   # C
        d = e = 0                                      # D, E: unpaid leave inputs
        f, g = d, e                                    # F, G: cumulative
        h = min(c, 1825) - f                           # H
        i = max(c - 1825, 0) - g                       # I
        k = round(h / 365 * salary * 0.5 + i / 365 * salary, 1)   # K
        out.append({"name": name, "C": c, "H": h, "I": i, "J": h + i, "K": k})
    return out


class WorkbookParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = fresh_app()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_cell_matches(self):
        from app.core import config, engine
        settings = config.load()
        checked = 0
        for year in (2023, 2024, 2025):
            year_end = datetime.date(year, 12, 31)
            for expected, (name, joining, salary) in zip(excel_rows(year_end), WORKBOOK):
                employee = {"id": 0, "name": name, "joining_date": joining,
                            "termination_date": None, "termination_reason": None}
                salaries = [{"effective_date": joining, "new_salary": salary}]
                got = engine.measure(employee, salaries, [], year_end, settings)
                self.assertEqual(got["service_days"], expected["C"], "%s %d C" % (name, year))
                self.assertEqual(got["days_first"], expected["H"], "%s %d H" % (name, year))
                self.assertEqual(got["days_later"], expected["I"], "%s %d I" % (name, year))
                self.assertEqual(got["net_service_days"], expected["J"], "%s %d J" % (name, year))
                self.assertAlmostEqual(got["entitlement"], expected["K"], 6,
                                       "%s %d K" % (name, year))
                checked += 5
        self.assertEqual(checked, 75)

    def test_rollforward_totals_match_workbook(self):
        from app.core import rollforward
        schedule = rollforward.build("2025-12-31")
        got = {b["year"]: b["totals"] for b in schedule["blocks"]}
        expected = {2023: (0.0, 105.2, 0.0, 105.2),
                    2024: (105.2, 401.1, 0.0, 506.3),
                    2025: (506.3, 2987.5, 0.0, 3493.8)}
        for year, (opening, charge, paid, closing) in expected.items():
            t = got[year]
            self.assertAlmostEqual(t["opening_provision"], opening, 1, "%d opening" % year)
            self.assertAlmostEqual(t["charge_for_year"], charge, 1, "%d charge" % year)
            self.assertAlmostEqual(t["benefits_paid"], paid, 1, "%d paid" % year)
            self.assertAlmostEqual(t["closing_provision"], closing, 1, "%d closing" % year)

    def test_roll_forward_identity_holds_every_year(self):
        from app.core import rollforward
        schedule = rollforward.build("2025-12-31")
        for block in schedule["blocks"]:
            for row in block["rows"]:
                self.assertAlmostEqual(
                    row["closing_provision"],
                    row["opening_provision"] + row["charge_for_year"] - row["benefits_paid"],
                    6, "identity failed for %s in %d" % (row["name"], block["year"]))

    def test_opening_equals_prior_closing(self):
        from app.core import rollforward
        schedule = rollforward.build("2025-12-31")
        previous = {}
        for block in schedule["blocks"]:
            for row in block["rows"]:
                self.assertAlmostEqual(row["opening_provision"],
                                       previous.get(row["employee_id"], 0.0), 6)
                previous[row["employee_id"]] = row["closing_provision"]


# --------------------------------------------------------------------------
# 2. Behaviour the workbook could not handle
# --------------------------------------------------------------------------
class BeyondTheWorkbook(unittest.TestCase):
    def setUp(self):
        self.tmp = fresh_app()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_years_extend_automatically_with_no_code_change(self):
        from app.core import rollforward
        for as_of, expected_last in (("2025-12-31", 2025), ("2031-06-30", 2031),
                                     ("2044-01-01", 2044)):
            schedule = rollforward.build(as_of)
            self.assertEqual(schedule["years"][0], 2023)
            self.assertEqual(schedule["years"][-1], expected_last)
            self.assertEqual(len(schedule["years"]),
                             expected_last - 2023 + 1, "no year may be skipped")

    def test_salary_change_uses_the_salary_in_force_each_year(self):
        from app.core import repo, rollforward
        employee = repo.create_employee({"name": "Salary Test", "joining_date": "2020-01-01",
                                         "monthly_salary": 1000})
        repo.add_salary(employee["id"], "2022-01-01", 2000, "Increase")
        schedule = rollforward.build("2023-12-31")
        by_year = {}
        for block in schedule["blocks"]:
            for row in block["rows"]:
                if row["employee_id"] == employee["id"]:
                    by_year[block["year"]] = row
        self.assertEqual(by_year[2021]["salary"], 1000.0)
        self.assertEqual(by_year[2022]["salary"], 2000.0)
        # 2020-01-01..2021-12-31 inclusive = 731 days at 1000
        self.assertAlmostEqual(by_year[2021]["entitlement"],
                               round(731 / 365 * 1000 * 0.5, 1), 6)
        # The raise creates a past-service catch-up in the year it happens.
        self.assertGreater(by_year[2022]["charge_for_year"],
                           by_year[2021]["charge_for_year"] * 2)

    def test_unpaid_leave_is_split_across_the_five_year_boundary(self):
        from app.core import config, engine
        settings = config.load()
        employee = {"id": 1, "name": "Leave", "joining_date": "2018-01-01",
                    "termination_date": None, "termination_reason": None}
        salaries = [{"effective_date": "2018-01-01", "new_salary": 3000}]
        # Day 1825 from 2018-01-01 is 2022-12-30, so this leave straddles it.
        leave = [{"start_date": "2022-12-26", "end_date": "2023-01-04"}]
        got = engine.measure(employee, salaries, leave, "2024-12-31", settings)
        self.assertEqual(got["leave_first"], 5, "26-30 Dec 2022 falls in the first band")
        self.assertEqual(got["leave_later"], 5, "31 Dec 2022 - 4 Jan 2023 falls after")
        self.assertEqual(got["days_first"], 1825 - 5)
        total = (datetime.date(2024, 12, 31) - datetime.date(2018, 1, 1)).days + 1
        self.assertEqual(got["days_later"], (total - 1825) - 5)

    def test_leave_beyond_the_reporting_date_is_ignored(self):
        from app.core import config, engine
        settings = config.load()
        employee = {"id": 1, "name": "Future leave", "joining_date": "2020-01-01",
                    "termination_date": None, "termination_reason": None}
        salaries = [{"effective_date": "2020-01-01", "new_salary": 1000}]
        leave = [{"start_date": "2026-01-01", "end_date": "2026-01-31"}]
        got = engine.measure(employee, salaries, leave, "2023-12-31", settings)
        self.assertEqual(got["leave_first"], 0)

    def test_excessive_leave_cannot_produce_a_negative_entitlement(self):
        from app.core import config, engine
        settings = config.load()
        employee = {"id": 1, "name": "Heavy leave", "joining_date": "2024-01-01",
                    "termination_date": None, "termination_reason": None}
        salaries = [{"effective_date": "2024-01-01", "new_salary": 1000}]
        leave = [{"start_date": "2024-01-01", "end_date": "2025-12-31"}]
        got = engine.measure(employee, salaries, leave, "2024-12-31", settings)
        self.assertEqual(got["days_first"], 0)
        self.assertEqual(got["days_later"], 0)
        self.assertEqual(got["entitlement"], 0.0)
        self.assertGreaterEqual(got["entitlement"], 0.0)

    def test_benefit_paid_to_a_serving_employee_keeps_provision_on_the_liability(self):
        """The workbook's charge definition fails here; the corrected one does not."""
        from app.core import repo, rollforward
        employee = repo.create_employee({"name": "Partial", "joining_date": "2020-01-01",
                                         "monthly_salary": 3000})
        repo.add_payment(employee["id"], "2023-06-30", 500, "Advance")
        schedule = rollforward.build("2024-12-31")
        for block in schedule["blocks"]:
            for row in block["rows"]:
                if row["employee_id"] != employee["id"]:
                    continue
                self.assertAlmostEqual(row["closing_provision"], row["entitlement"], 6,
                                       "provision must equal the measured liability")
                self.assertAlmostEqual(
                    row["closing_provision"],
                    row["opening_provision"] + row["charge_for_year"] - row["benefits_paid"], 6)
        # The workbook method would have left the provision 500 short.
        row_2024 = [r for b in schedule["blocks"] if b["year"] == 2024
                    for r in b["rows"] if r["employee_id"] == employee["id"]][0]
        self.assertAlmostEqual(row_2024["reconciling_difference"], 0.0, 6)
        row_2023 = [r for b in schedule["blocks"] if b["year"] == 2023
                    for r in b["rows"] if r["employee_id"] == employee["id"]][0]
        self.assertAlmostEqual(row_2023["reconciling_difference"], 500.0, 6)

    def test_termination_freezes_service_and_settlement_clears_the_provision(self):
        from app.core import repo, rollforward
        employee = repo.create_employee({"name": "Leaver", "joining_date": "2020-01-01",
                                         "monthly_salary": 3000,
                                         "termination_date": "2024-06-30",
                                         "termination_reason": "End of Contract"})
        schedule = rollforward.build("2025-12-31")
        rows = {b["year"]: [r for r in b["rows"] if r["employee_id"] == employee["id"]][0]
                for b in schedule["blocks"]}
        self.assertEqual(rows[2024]["calculation_date"], "2024-06-30")
        self.assertEqual(rows[2025]["calculation_date"], "2024-06-30",
                         "service must not keep accruing after leaving")
        self.assertAlmostEqual(rows[2025]["entitlement"], rows[2024]["entitlement"], 6)
        self.assertAlmostEqual(rows[2025]["charge_for_year"], 0.0, 6)

        repo.add_payment(employee["id"], "2024-07-15", rows[2024]["payable"], "Settlement")
        schedule = rollforward.build("2025-12-31")
        rows = {b["year"]: [r for r in b["rows"] if r["employee_id"] == employee["id"]][0]
                for b in schedule["blocks"]}
        self.assertAlmostEqual(rows[2024]["closing_provision"], 0.0, 6,
                               "a full settlement must clear the provision")
        self.assertAlmostEqual(rows[2025]["closing_provision"], 0.0, 6)

    def test_article_85_reduces_the_amount_payable_on_resignation(self):
        from app.core import config, engine
        settings = config.load()
        salaries = [{"effective_date": "2018-01-01", "new_salary": 3000}]

        def payable(reason, as_of):
            employee = {"id": 1, "name": "R", "joining_date": "2018-01-01",
                        "termination_date": as_of, "termination_reason": reason}
            return engine.measure(employee, salaries, [], as_of, settings)

        short = payable("Resignation", "2019-06-30")      # under 2 years
        self.assertEqual(short["payable"], 0.0)
        self.assertGreater(short["entitlement"], 0.0)

        mid = payable("Resignation", "2021-06-30")        # 2 to 5 years
        self.assertAlmostEqual(mid["payable"], round(mid["entitlement"] / 3.0, 1), 1)

        senior = payable("Resignation", "2025-06-30")     # 5 to 10 years
        self.assertAlmostEqual(senior["payable"], round(senior["entitlement"] * 2 / 3.0, 1), 1)

        dismissed = payable("Dismissal", "2021-06-30")    # Article 84 in full
        self.assertAlmostEqual(dismissed["payable"], dismissed["entitlement"], 6)

    def test_status_always_agrees_with_the_termination_date(self):
        from app.core import repo
        employee = repo.create_employee({"name": "Status", "joining_date": "2022-01-01",
                                         "monthly_salary": 1000, "status": "Terminated"})
        self.assertEqual(employee["status"], "Active",
                         "no termination date means Active regardless of what was sent")
        updated = repo.update_employee(employee["id"], {"termination_date": "2024-03-31"})
        self.assertEqual(updated["status"], "Terminated")
        reverted = repo.update_employee(employee["id"], {"termination_date": None})
        self.assertEqual(reverted["status"], "Active")

    def test_non_calendar_financial_year_end(self):
        from app.core import config, rollforward
        config.save({"year_end_month": 6, "year_end_day": 30})
        schedule = rollforward.build("2025-12-31")
        self.assertTrue(all(b["year_end"].endswith("-06-30") for b in schedule["blocks"]))
        block = rollforward.current_block(schedule)
        self.assertEqual(block["year_end"], "2026-06-30")
        config.save({"year_end_month": 12, "year_end_day": 31})

    def test_backup_and_restore_round_trip(self):
        from app.core import backup, repo
        repo.create_employee({"name": "Backup Case", "joining_date": "2021-01-01",
                              "monthly_salary": 7500})
        before = len(repo.list_employees())
        archive = backup.create(os.path.join(self.tmp, "bk"))["path"]
        repo.delete_employee(repo.list_employees()[0]["id"])
        self.assertEqual(len(repo.list_employees()), before - 1)
        backup.restore(archive)
        self.assertEqual(len(repo.list_employees()), before)

    def test_deleting_an_employee_removes_dependent_records(self):
        from app.core import db, repo
        employee = repo.create_employee({"name": "Cascade", "joining_date": "2021-01-01",
                                         "monthly_salary": 1000})
        repo.add_leave(employee["id"], "2022-01-01", "2022-01-05")
        repo.add_payment(employee["id"], "2022-02-01", 100)
        repo.delete_employee(employee["id"])
        for table in ("salary_history", "unpaid_leave", "benefits_paid"):
            left = db.one("SELECT COUNT(*) AS c FROM %s WHERE employee_id = ?" % table,
                          (employee["id"],))["c"]
            self.assertEqual(left, 0, "%s should cascade" % table)

    def test_an_employee_must_keep_one_salary_record(self):
        from app.core import repo
        employee = repo.create_employee({"name": "Only Salary", "joining_date": "2021-01-01",
                                         "monthly_salary": 1000})
        record = repo.list_salaries(employee["id"])[0]
        self.assertRaises(ValueError, repo.delete_salary, record["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

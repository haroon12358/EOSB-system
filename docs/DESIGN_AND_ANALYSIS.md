# EOSB Management System — Workbook Analysis and System Design

---

## Part 1 — What the workbook actually does

The source file `ESB_Provision_Rollforward.xlsx` contains two sheets.

### Sheet `Employees` — the input

Seven columns, all manual inputs, five employee rows:

| Col | Field | Notes |
|-----|-------|-------|
| A | Number | sequence 1–5 |
| B | Identity Number | national ID, stored as text |
| C | Employee Name | |
| D | Joining Date | |
| E | Employment Status | `Active` for all five |
| F | Termination Date | blank for all five |
| G | Monthly Salary | a single current figure |

### Sheet `Provision Schedule` — the calculation

Two control cells drive everything:

- `D4` = reporting year end, hard-typed as `31-Dec-2025`
- `D5` = `YEAR(MIN(Employees!D5:D9))` → 2023

Below them sit **exactly three** repeating blocks of fifteen columns:

| Block | Rows | Year end formula | Resolves to |
|-------|------|------------------|-------------|
| 1 | 9–14 | `=DATE($D$5,12,31)` | 2023-12-31 |
| 2 | 18–23 | `=DATE($D$5+1,12,31)` | 2024-12-31 |
| 3 | 27–32 | `=$D$4` | 2025-12-31 |

### The formulas, column by column

Taking row 27 (employee 1, year 3) as the representative case:

| Col | Heading | Formula | Meaning |
|-----|---------|---------|---------|
| B | Calculation Date | `=IF(Employees!F5="",$C$25,MIN(Employees!F5,$C$25))` | year end, or termination date once the employee has left |
| C | Service Days at Year End | `=IF(Employees!D5>B27,0,B27-Employees!D5+1)` | **inclusive** day count; zero before joining |
| D | Unpaid Leave in First 5 Years | `0` | manual input, this year only |
| E | Unpaid Leave After 5 Years | `0` | manual input, this year only |
| F | Total Unpaid Leave in First 5 Years | `=D27+F18` | running cumulative |
| G | Total Unpaid Leave After 5 Years | `=E27+G18` | running cumulative |
| H | Days in First 5 Years | `=MIN(C27,1825)-F27` | service inside the first band, net of leave |
| I | Days Over 5 Years | `=MAX(C27-1825,0)-G27` | service beyond, net of leave |
| J | Net Service Days | `=H27+I27` | |
| K | Entitlement at Year End | `=ROUND(H27/365*Employees!G5*0.5+I27/365*Employees!G5,1)` | the award |
| L | Opening Provision | `=O18` (prior year closing); `0` in year 1 | |
| M | Charge for the Year | `=K27-K18` (change in entitlement); `=K9` in year 1 | |
| N | Benefits Paid During Year | `0` | manual input |
| O | Closing Provision | `=L27+M27-N27` | |

Row 14 / 23 / 32 total columns K through O.

### The accounting rule expressed

```
Entitlement = (days in first 5 years ÷ 365 × monthly salary × 0.5)
            + (days beyond 5 years  ÷ 365 × monthly salary × 1.0)
```

This is **Article 84 of the Saudi Labour Law**: half a month's wage for each of
the first five years of service, a full month's wage for each year thereafter,
pro-rated by day. `1825` is five years expressed in days.

### Figures the workbook produces

The file was never recalculated, so no cached values are stored in it. The
formulas were re-derived independently and produce:

| Year ended | Opening | Charge | Paid | Closing |
|-----------:|--------:|-------:|-----:|--------:|
| 2023-12-31 | 0.0 | 105.2 | 0.0 | **105.2** |
| 2024-12-31 | 105.2 | 401.1 | 0.0 | **506.3** |
| 2025-12-31 | 506.3 | 2,987.5 | 0.0 | **3,493.8** |

Per employee at 31-Dec-2025: Abdulrazzaq 906.3, Mahmoud 1,200.0,
Al-Zahrani (Omar) 169.9, Al-Zahrani (Rayana) 1,178.1, Khalid 39.5.

**The application reproduces all of these to the decimal.** The test suite
re-implements the workbook formulas independently and asserts agreement on
75 individual cells across three years and five employees.

---

## Part 2 — Problems found in the workbook

Ranked by how much damage each one can do.

### 2.1 Only three year-blocks exist, and the third is not sequential — *critical*

Block 3 is `=$D$4`, not `=DATE($D$5+2,12,31)`. Set `D4` to 2027 and the
schedule reads 2023 → 2024 → **2027**. Two years vanish. Worse, the charge in
the 2027 block is computed as `K2027 − K2024`, three years of accrual reported
as one year's expense, while 2025 and 2026 are never reported at all. The
workbook silently produces a wrong income statement rather than failing.

**Resolved:** the schedule is generated, one block per financial year, from the
earliest joining year through to the current reporting year. Adding a year
requires nothing. A test asserts no year can ever be skipped, at reporting
dates out to 2044.

### 2.2 Closing Provision can permanently diverge from the liability — *critical*

The workbook defines `Charge = ΔEntitlement` and lets Closing fall out of
`Opening + Charge − Paid`. That identity only holds while `Paid` is always
zero. Pay a serving employee 500 as an advance and the closing provision sits
500 below the measured obligation — **in that year and in every year
afterwards**, because the charge never catches up.

**Resolved:** the closing balance is anchored to the measured obligation and
the charge becomes the balancing figure:

```
Closing Provision = measured entitlement (or, once settled, the unpaid remainder)
Charge for the Year = Closing − Opening + Benefits Paid
```

With no benefits paid the two methods are arithmetically identical, so the
workbook's comparatives are unaffected — verified by test. The workbook's
figure is still reported as `charge_excel_method` alongside a
`reconciling_difference` so the two can be tied out.

### 2.3 The Employment Status column is decorative — *high*

No formula anywhere reads `Employees!E`. Termination is driven purely by the
presence of a date in column F. An employee marked `Terminated` with no date
in F keeps accruing indefinitely, and nothing flags the contradiction.

**Resolved:** status is derived from the termination date and cannot contradict
it. A test asserts this in both directions.

### 2.4 No floor on the banded day counts — *high*

`H = MIN(C,1825) − F` and `I = MAX(C−1825,0) − G` are unclamped. Cumulative
unpaid leave larger than the banded service produces negative days and a
**negative entitlement** — a contra-liability that would flow straight into the
accounts. Column I is also negative for any employee with post-five-year leave
recorded before they actually pass five years.

**Resolved:** both bands are floored at zero, with a test using two years of
continuous unpaid leave against one year of service.

### 2.5 Unpaid leave must be classified by hand — *medium*

Columns D and E require the user to decide whether each leave day falls inside
the first five years or after. For leave straddling the boundary the user must
split a single absence across two columns and get the split right.

**Resolved:** leave is entered once as a date range and the split is derived
from the dates. A test uses an absence deliberately straddling day 1825 and
asserts the 5/5 split.

### 2.6 Salary is a single figure applied retroactively — *medium*

Changing column G restates every prior year's entitlement and charge. Last
year's audited comparative moves because someone got a raise this year.

**Resolved:** salary is never overwritten. Each change is stored with an
effective date, and each reporting year uses the salary in force at that year
end — the correct measurement basis under both Saudi law and IAS 19. The
consequence is that a raise produces a past-service catch-up in the year it
happens, which is correct treatment, and is asserted by test.

### 2.7 Article 85 is not modelled — *medium*

The workbook always books the full Article 84 award. Article 85 scales the
award down for an employee who **resigns**: nothing below two years, one third
from two to five, two thirds from five to ten, full above ten. Paying out the
full award on a resignation over-settles.

**Resolved:** the provision continues to carry the full Article 84 award, which
is the conservative and standard treatment, but a reason for leaving is
captured on termination and the amount **legally payable** is scaled. The
difference is disclosed as a settlement adjustment and released through the
charge. Configurable, and tested at each threshold.

### 2.8 Settled leavers are never cleared — *medium*

Once terminated, the workbook freezes the entitlement and keeps re-reporting
it forever with a zero charge. If a settlement is paid, the provision goes to
zero only by coincidence of the arithmetic, and any shortfall or excess lingers
in the balance indefinitely.

**Resolved:** a leaver's obligation is `amount payable − cumulative benefits
paid`, floored at zero. A full settlement clears the provision and it stays
cleared. Tested.

### 2.9 `1825` days is not exactly five years — *low*

Any five-year span containing a leap day is 1,826 days, so employees crossing
the boundary in a leap period enter the full-month band roughly one day early.
The effect is a fraction of one day's wage.

**Retained deliberately** to preserve exact agreement with the workbook, but
exposed as a setting rather than a magic number.

### 2.10 `B − joining + 1` counts both endpoints — *low*

27-Sep-2023 to 31-Dec-2023 is reported as 96 days rather than 95. Marginally
generous, but applied consistently. **Retained** for exact parity.

### 2.11 No validation anywhere — *low*

Nothing prevents duplicate identity numbers, a termination date before the
joining date, or a text value in a salary cell.

**Resolved:** validated at the API boundary with clear messages.

### 2.12 Everything is a magic number — *low*

`1825`, `365`, `0.5` and the rounding are embedded in 15 copies of the same
formula. A change in law means editing every one.

**Resolved:** all are settings, editable in the interface, with the live
formula displayed back to the user.

### 2.13 No discounting — *disclosure only*

The workbook measures an undiscounted accrued liability. A full IAS 19
defined-benefit measurement would discount the obligation and allow for salary
growth and employee turnover. For an entity of this size the undiscounted
"legal liability" method is common and generally accepted, but it is an
accounting policy choice and should be stated as one. **No change made** — this
is a decision for the reporting entity and its auditor, not for software.

---

## Part 3 — Architecture

Five layers, each independently testable, with dependencies pointing one way only.

```
  Browser  ──HTTP──▶  Server  ──▶  API  ──▶  Repository  ──▶  SQLite
  (app/web)          (server.py)  (api.py)    (repo.py)     (data/eosb.db)
                                      │
                                      ├──▶  Calculation engine   (engine.py)      pure
                                      ├──▶  Roll forward         (rollforward.py) pure
                                      └──▶  Reports              (reports/)
```

The calculation engine performs no database access and has no side effects. It
takes an employee, their salary records, their leave records, a date and a
settings dictionary, and returns numbers. This is what makes cell-for-cell
verification against the workbook possible.

### Module map

| File | Responsibility |
|------|----------------|
| `app/core/config.py` | Settings and path resolution — every path derives from the folder this file lives in |
| `app/core/clock.py` | Reporting date: internet first, system clock as fallback |
| `app/core/dates.py` | Date parsing, financial year ends, inclusive range overlap |
| `app/core/db.py` | Schema, connection, immediate commit, audit log, seed data |
| `app/core/repo.py` | CRUD for employees, salary history, leave, payments |
| `app/core/engine.py` | **The entitlement calculation** — pure functions |
| `app/core/rollforward.py` | Year-by-year schedule assembly and dashboard aggregates |
| `app/core/api.py` | Routing, validation, error messages |
| `app/core/server.py` | Loopback HTTP server, static files, JSON dispatch |
| `app/core/backup.py` | Backup creation, inspection, safe restore |
| `app/reports/xlsx.py` | Dependency-free `.xlsx` writer |
| `app/reports/pdf.py` | Dependency-free PDF writer with pagination |
| `app/reports/builders.py` | The four reports in both formats |
| `app/web/` | Interface — one HTML, one CSS, one JS file |
| `tests/test_engine.py` | 17 tests, including 75 workbook parity assertions |

---

## Part 4 — Database design

SQLite, single file, at `data/eosb.db`, journal mode `TRUNCATE`.

`TRUNCATE` rather than `WAL` is a deliberate choice: WAL leaves `-wal` and
`-shm` side files that must be checkpointed before the folder can be copied
safely, and it fails outright on some network shares and removable drives.
A single-file journal keeps the folder genuinely portable.

```
employees
  id                 INTEGER PK
  employee_no        TEXT          -- display sequence
  identity_number    TEXT          -- validated unique when present
  name               TEXT NOT NULL
  joining_date       TEXT NOT NULL -- ISO yyyy-mm-dd
  termination_date   TEXT          -- NULL while serving
  termination_reason TEXT          -- drives the Article 85 factor
  status             TEXT          -- derived, never contradicts the date
  department, position, notes
  created_at, updated_at

salary_history                     -- salary is never overwritten
  id, employee_id → employees(id) ON DELETE CASCADE
  effective_date, previous_salary, new_salary, reason, created_at

unpaid_leave                       -- band split derived from the dates
  id, employee_id → employees(id) ON DELETE CASCADE
  start_date, end_date, days, reason, created_at

benefits_paid
  id, employee_id → employees(id) ON DELETE CASCADE
  payment_date, amount, reference, notes, created_at

audit_log                          -- every create, update, delete, backup, report
  id, at, entity, entity_id, action, detail

meta                               -- schema version, seed marker
  key, value
```

Foreign keys are enforced and cascade. Every write commits immediately —
there is no save button and no unsaved state.

---

## Part 5 — Folder structure

```
EOSB_System/
├── EOSB.bat                  ← double-click this (Windows)
├── EOSB.command              ← double-click this (Mac / Linux)
├── README.txt
├── app/
│   ├── main.py               entry point, single-instance guard, browser launch
│   ├── core/                 config, clock, dates, db, repo, engine,
│   │                         rollforward, api, server, backup
│   ├── reports/              xlsx, pdf, builders
│   └── web/                  index.html, app.css, app.js
├── data/
│   └── eosb.db               ← all your data, one file
├── config/
│   └── settings.json
├── backups/                  copies kept inside the folder
├── runtime/                  the runtime (created once by SETUP_RUNTIME.bat)
├── tools/
│   └── SETUP_RUNTIME.bat     one-time, needs internet, run once ever
├── docs/
└── tests/
```

**Folder behaviour.** `config.py` resolves every path from its own location, so
the application always uses the database beside it. The launcher uses `%~dp0`,
the directory the batch file itself lives in — so a desktop shortcut opens the
database belonging to that folder and never another copy. Move the folder,
copy it to a USB stick, send it to a client: the data travels with it.

**Second launch.** Double-clicking again while it is running detects the
existing instance, verifies it belongs to this same folder, and reopens the
browser tab rather than starting a second server.

---

## Part 6 — Technology

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3, **standard library only** | no packages to install, nothing to break, works offline permanently |
| Database | SQLite via `sqlite3` | in the standard library; real transactions and foreign keys; one portable file |
| Server | `http.server` on `127.0.0.1` | loopback only, never exposed to the network |
| Frontend | Plain HTML, CSS, JavaScript | no build step, no CDN, no framework to age out; opens in any browser |
| Excel export | `zipfile` + XML, written here | an `.xlsx` is a zip of XML; writing it directly avoids a dependency |
| PDF export | written here, base-14 fonts | no font files, no library |

There are **zero third-party dependencies**. That is what makes the portable
folder possible: nothing can fail to install, and nothing needs updating.

---

## Part 7 — Things worth knowing

- **Amounts.** All figures are in the currency set in Settings, default SAR.
  Entitlements round to one decimal, matching the workbook.
- **PDF and Arabic.** The PDF writer uses the base-14 fonts, which cover Latin
  characters. Names in Arabic script export correctly to Excel but will not
  render in PDF. If Arabic PDFs are needed, that requires embedding a Unicode
  font — a contained change to `reports/pdf.py`.
- **Financial year end** is configurable. It defaults to 31 December but
  supports any month and day, and the schedule follows it.
- **Projected years.** Years ending after today are shown and marked
  *projected*; they measure service to today, not to the future year end, so
  they never overstate the liability.
- **The audit log** records every change and is queryable at `/api/audit`.

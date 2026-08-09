"""Self-check. Writes diagnostic_report.txt in the application folder."""
import datetime
import os
import platform
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

lines = []


def say(text=""):
    lines.append(text)
    try:
        print(text)
    except Exception:
        pass


say("=" * 68)
say(" EOSB MANAGEMENT SYSTEM - DIAGNOSTIC REPORT")
say(" " + datetime.datetime.now().strftime("%d %B %Y  %H:%M:%S"))
say("=" * 68)
say()
say("ENVIRONMENT")
say("  Python version : %s" % sys.version.replace("\n", " "))
say("  Python path    : %s" % sys.executable)
say("  Platform       : %s %s" % (platform.system(), platform.release()))
say("  Script folder  : %s" % HERE)
say("  App folder     : %s" % ROOT)
say()

ok = True

say("REQUIRED MODULES")
for name in ("sqlite3", "http.server", "json", "zipfile", "webbrowser", "urllib.request"):
    try:
        __import__(name)
        say("  %-16s OK" % name)
    except Exception as exc:
        ok = False
        say("  %-16s MISSING  (%s)" % (name, exc))
say()

say("FOLDERS")
for name in ("app", "app/core", "app/web", "app/reports", "data", "config"):
    path = os.path.join(ROOT, name.replace("/", os.sep))
    exists = os.path.isdir(path)
    if not exists:
        ok = False
    say("  %-14s %s   %s" % (name, "found" if exists else "MISSING", path))
say()

say("KEY FILES")
for name in ("app/main.py", "app/web/index.html", "app/web/app.js", "app/web/app.css"):
    path = os.path.join(ROOT, name.replace("/", os.sep))
    exists = os.path.isfile(path)
    if not exists:
        ok = False
    say("  %-22s %s" % (name, "found" if exists else "MISSING"))
say()

say("CAN THIS FOLDER BE WRITTEN TO?")
probe = os.path.join(ROOT, "data", "_write_test.tmp")
try:
    os.makedirs(os.path.dirname(probe), exist_ok=True)
    with open(probe, "w") as fh:
        fh.write("test")
    os.remove(probe)
    say("  YES - the application can save your data here.")
except Exception as exc:
    ok = False
    say("  NO  - %s" % exc)
    say("  >> Nothing you enter can be saved.")
    say("  >> This happens when the folder is opened from inside the ZIP,")
    say("  >> or placed somewhere Windows protects. Extract the ZIP to your")
    say("  >> Documents or Desktop and run it from there.")
say()

say("DATABASE")
try:
    from app.core import config, db
    say("  Location : %s" % config.DB_PATH)
    result = db.initialise()
    if result.get("repaired"):
        say("  NOTE     : an unreadable database was moved to %s" % result["repaired"])
    report = db.health()
    for key in ("exists", "size", "writable", "integrity", "employees",
                "salary_history", "unpaid_leave", "benefits_paid"):
        say("  %-15s %s" % (key, report.get(key)))
    if not report.get("ok"):
        ok = False
        say("  ERROR    : %s" % report.get("error"))
except Exception:
    ok = False
    say("  FAILED to open the database:")
    say(traceback.format_exc())
say()

say("CALCULATION CHECK (against the original workbook)")
try:
    from app.core import rollforward
    schedule = rollforward.build("2025-12-31")
    expected = {2023: 105.2, 2024: 506.3, 2025: 3493.8}
    for block in schedule["blocks"]:
        year = block["year"]
        if year in expected:
            got = block["totals"]["closing_provision"]
            match = abs(got - expected[year]) < 0.05
            if not match:
                ok = False
            say("  %d closing provision  %10.1f   expected %10.1f   %s"
                % (year, got, expected[year], "MATCH" if match else "MISMATCH"))
except Exception:
    ok = False
    say("  FAILED:")
    say(traceback.format_exc())
say()

say("LOCAL SERVER")
try:
    import json
    import urllib.request
    from app.core import server
    httpd, port = server.serve()
    url = "http://127.0.0.1:%d/api/health" % port
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read())
    say("  Started on port %d and answered correctly." % port)
    say("  Employees visible through the server: %s" % payload.get("employees"))
    with urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=10) as response:
        say("  Interface page: HTTP %s, %s bytes"
            % (response.status, len(response.read())))
    httpd.shutdown()
except Exception:
    ok = False
    say("  FAILED to start the local server:")
    say(traceback.format_exc())
    say("  >> Antivirus or a firewall may be blocking it.")
say()

say("=" * 68)
say(" RESULT: %s" % ("EVERYTHING PASSED - the application should work."
                     if ok else "PROBLEMS FOUND - see the lines marked above."))
say("=" * 68)

target = os.path.join(ROOT, "diagnostic_report.txt")
try:
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    say("")
    say("Saved to: %s" % target)
    say("Send that file to get this resolved.")
except Exception as exc:
    say("Could not save the report: %s" % exc)

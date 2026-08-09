"""Entry point.

Starts the local server, opens the default browser and stays running until
the window is closed or the process is stopped.
"""
import os
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import clock, config, db, server   # noqa: E402


def already_running(port):
    """True when this same application folder is already serving on the port."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/meta" % port, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return os.path.normcase(payload.get("root", "")) == os.path.normcase(config.ROOT_DIR)
    except Exception:
        return False


def main():
    # A second double-click should reuse the running window, not start again.
    preferred = int(config.get("preferred_port", 8731))
    if already_running(preferred):
        url = "http://127.0.0.1:%d/" % preferred
        print("\n  Already running - reopening %s\n" % url)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return

    db.initialise()
    today = clock.today()

    httpd, port = server.serve()
    url = "http://127.0.0.1:%d/" % port

    banner = [
        "", "  %s  v%s" % (config.APP_NAME, config.APP_VERSION),
        "  " + "-" * 58,
        "  Folder     : %s" % config.ROOT_DIR,
        "  Database   : %s" % config.DB_PATH,
        "  Reporting  : %s  (%s date)" % (today.isoformat(), clock.source()),
        "  Address    : %s" % url,
        "",
        "  If your browser did not open, type the address above into it.",
        "  The application is running. Close this window to stop it.", "",
    ]
    for line in banner:
        try:
            print(line)
        except Exception:
            pass

    if config.get("open_browser", True):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()


def _crash(exc):
    """Write the failure somewhere the user can find and read it."""
    import traceback
    detail = traceback.format_exc()
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        path = os.path.join(config.LOG_DIR, "startup.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("%s\n\nPython : %s\nFolder : %s\nDatabase: %s\n"
                     % (detail, sys.version, config.ROOT_DIR, config.DB_PATH))
    except Exception:
        path = "(could not be written)"
    print("")
    print("  " + "=" * 62)
    print("  THE APPLICATION COULD NOT START")
    print("  " + "=" * 62)
    print("")
    print(detail)
    print("  Python   : %s" % sys.version.split()[0])
    print("  Folder   : %s" % config.ROOT_DIR)
    print("  Database : %s" % config.DB_PATH)
    print("")
    print("  This was also written to: %s" % path)
    print("  Send that file and the text above to get this fixed.")
    print("")
    try:
        input("  Press Enter to close this window. ")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        _crash(exc)

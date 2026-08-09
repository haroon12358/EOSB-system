"""Local HTTP server.

Binds to the loopback interface only, so the application is never exposed to
the network.  Static files are served from app/web and everything under /api
is handled as JSON.
"""
import json
import mimetypes
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import api, config, db

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

MAX_BODY = 8 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "EOSB/" + config.APP_VERSION
    # HTTP/1.0 with an explicit close. Keep-alive on a threaded local server
    # can leave a browser waiting on a connection it will never get an answer
    # on, which shows up as a page that loads but never fills with data.
    protocol_version = "HTTP/1.0"

    # Keep the console quiet; the audit log records what matters.
    def log_message(self, fmt, *args):
        pass

    # -- helpers -----------------------------------------------------------
    def _send(self, status, body=b"", content_type="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, data):
        self._send(status, json.dumps(data, default=str), "application/json")

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise api.ApiError("Request too large.", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise api.ApiError("Malformed request.")

    # -- static ------------------------------------------------------------
    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        relative = unquote(path.lstrip("/"))
        target = os.path.normpath(os.path.join(config.WEB_DIR, relative))
        if not target.startswith(os.path.normpath(config.WEB_DIR)):
            return self._send(403, b"Forbidden", "text/plain")
        if not os.path.isfile(target):
            # Unknown paths fall back to the single page application.
            target = os.path.join(config.WEB_DIR, "index.html")
            if not os.path.isfile(target):
                return self._send(404, b"Not found", "text/plain")
        kind = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind == "application/javascript":
            kind += "; charset=utf-8"
        with open(target, "rb") as fh:
            self._send(200, fh.read(), kind)

    # -- dispatch ----------------------------------------------------------
    def _dispatch(self, method):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if method in ("GET", "HEAD"):
                return self._static(parsed.path)
            return self._send(405, b"Method not allowed", "text/plain")
        try:
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            payload = self._body() if method in ("POST", "PUT", "PATCH") else {}
            result = api.handle(method, parsed.path, query, payload)
            self._json(200, result)
        except api.ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:  # last resort, never lose the server
            import traceback
            detail = traceback.format_exc()
            try:
                with open(os.path.join(config.LOG_DIR, "errors.log"), "a",
                          encoding="utf-8") as fh:
                    fh.write("\n--- %s %s ---\n%s" % (method, self.path, detail))
            except Exception:
                pass
            self._json(500, {"error": "Unexpected error: %s" % exc, "detail": detail})

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def process_request_thread(self, request, client_address):
        try:
            ThreadingHTTPServer.process_request_thread(self, request, client_address)
        finally:
            db.close()


def find_port(preferred):
    """Use the preferred port when free, otherwise the next available one."""
    for candidate in [preferred] + list(range(preferred + 1, preferred + 40)) + [0]:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", candidate))
            port = probe.getsockname()[1]
            probe.close()
            return port
        except OSError:
            continue
    raise RuntimeError("No free port available.")


def serve(port=None):
    port = port or find_port(int(config.get("preferred_port", 8731)))
    httpd = Server(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port

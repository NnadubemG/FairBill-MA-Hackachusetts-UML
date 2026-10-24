"""Thin stdlib HTTP adapter over the pure routing core. No new dependencies.

    python -m app_server.server [--host 127.0.0.1] [--port 8000] [--data DIR]

Serves the web app (GET /, /app/*, /src/compare/*) and the JSON API from one origin.
Host/port may also come from the HOST / PORT environment variables (containers).
Never logs request bodies, query strings, or uploaded content.
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .app import ROUTES, SECURITY_HEADERS, AppContext, route, static_file

MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MB cap (bills/images); rejects larger bodies.
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")


def make_handler(ctx: AppContext) -> type[BaseHTTPRequestHandler]:
    class AppHandler(BaseHTTPRequestHandler):
        server_version = "FairBill"
        sys_version = ""

        def log_message(self, *args, **kwargs):  # silence; never log bodies/queries
            return

        def _headers(self, status: int, content_type: str, length: int, cache: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", cache)
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(data), "no-store")
            self.wfile.write(data)

        def do_OPTIONS(self):  # noqa: N802 - CORS preflight
            self._headers(204, "text/plain", 0, "no-store")

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in ROUTES:
                found = static_file(parsed.path)
                if found is not None:
                    content_type, body = found
                    self._headers(200, content_type, len(body), "no-cache")
                    self.wfile.write(body)
                    return
            status, payload = route(ctx, "GET", parsed.path, parse_qs(parsed.query), None)
            self._send(status, payload)

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, {"error": "invalid Content-Length"})
                return
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "request body too large (max 8 MB)"})
                return
            body = None
            if length:
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send(400, {"error": "request body must be valid JSON"})
                    return
            status, payload = route(ctx, "POST", parsed.path, parse_qs(parsed.query), body)
            self._send(status, payload)

    return AppHandler


def build_server(data_dir: str | None, port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    ctx = AppContext.build(data_dir)
    return ThreadingHTTPServer((host, port), make_handler(ctx))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app_server.server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--data", default=None, help="processed data dir (default: config)")
    args = parser.parse_args(argv)

    httpd = build_server(args.data, args.port, args.host)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print(f"FairBill MA running at http://{shown}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

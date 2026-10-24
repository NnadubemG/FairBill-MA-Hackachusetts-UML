"""Thin stdlib HTTP adapter over the pure routing core. No new dependencies.

    python -m app_server.server [--port 8000] [--data DIR]

Loads the app context once at startup. Parses method/path/query/JSON body, calls
route(), writes a JSON response with CORS enabled. Never logs request bodies.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .app import AppContext, route

MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MB cap (bills/images); rejects larger bodies.


def make_handler(ctx: AppContext) -> type[BaseHTTPRequestHandler]:
    class AppHandler(BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):  # silence; never log bodies/queries
            return

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):  # CORS preflight
            self._send(204, {})

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            status, payload = route(ctx, "GET", parsed.path, query, None)
            self._send(status, payload)

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "request body too large"})
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


def build_server(data_dir: str | None, port: int) -> ThreadingHTTPServer:
    ctx = AppContext.build(data_dir)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctx))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app_server.server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default=None, help="processed data dir (default: config)")
    args = parser.parse_args(argv)

    httpd = build_server(args.data, args.port)
    print(f"app server on http://127.0.0.1:{args.port}")
    print("  GET  /health")
    print("  GET  /procedures")
    print("  GET  /compare?code=99213")
    print("  POST /analyze    {line_items:[...]}")
    print("  POST /extract    {content_type, document_base64}")
    print("  POST /letter     {letter_type, patient, flags, line_items}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Thin stdlib HTTP adapter over the compare service. No new dependencies.

Routes:
    GET /procedures          -> list_procedures(store)
    GET /compare?code=XXXXX  -> compare(store, code); missing code -> 400
    anything else            -> 404

Loads the Store once at startup. Does not log request bodies or query values.
Serializes with the pipeline's deterministic jsonio.dumps.

Run locally:
    python -m backend.compare.server --port 8000 --data data/processed
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from pipeline import jsonio

from . import service
from .store import Store


def make_handler(store: Store) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to a loaded Store."""

    class CompareHandler(BaseHTTPRequestHandler):
        # Silence default request logging (avoid logging query values; keep output quiet).
        def log_message(self, *args, **kwargs):  # noqa: D401
            return

        def _send(self, status: int, payload: dict | list) -> None:
            body = jsonio.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # CORS: harmless for a read-only public-data lookup; lets the front end call it.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/procedures":
                self._send(200, service.list_procedures(store))
                return
            if parsed.path == "/compare":
                params = parse_qs(parsed.query)
                codes = params.get("code")
                if not codes or not codes[0].strip():
                    self._send(400, {"error": "missing required query parameter: code"})
                    return
                self._send(200, service.compare(store, codes[0]))
                return
            self._send(404, {"error": "not found"})

    return CompareHandler


def build_server(data_dir: str, port: int) -> HTTPServer:
    store = Store.load(data_dir)
    return HTTPServer(("127.0.0.1", port), make_handler(store))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.compare.server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default="data/processed")
    args = parser.parse_args(argv)

    httpd = build_server(args.data, args.port)
    print(f"compare API on http://127.0.0.1:{args.port}  (data: {args.data})")
    print("  GET /procedures")
    print("  GET /compare?code=99213")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

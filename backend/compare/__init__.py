"""Read-only compare/lookup service over the pipeline's processed JSON.

Pure lookup functions (service.py) over an in-memory Store (store.py). A thin stdlib
http.server (server.py) exposes GET /procedures and GET /compare. No database, no writes,
no outbound network, no new dependencies.
"""

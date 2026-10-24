"""Bill extraction (`/backend/extract`).

Turns an uploaded hospital bill into validated ``LineItem`` objects (from
``/contracts``) plus bill-level metadata. The model does extraction only: it never
produces flags and never guesses billing codes.

Owner: Sam. This package does not redefine any ``/contracts`` type.
"""

"""Letter drafts (`/backend/letter`).

Builds an editable letter from a fixed template. Patient fields are inserted by the
template only. The model may write one short "reason" paragraph (coding review only), and
code checks it. If it fails any check, or the model call fails, a fixed fallback
paragraph is used.

Owner: Sam. This package does not redefine any ``/contracts`` type.
"""

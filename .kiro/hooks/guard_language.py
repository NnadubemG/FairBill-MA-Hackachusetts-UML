"""PreToolUse guard. Script-based: no model calls, stdlib only.

Reads the hook JSON from stdin and blocks (exit 2, reason on stderr) a file write that:
  1. puts a banned word into product-facing code or copy, or
  2. adds `.kiro` to a .gitignore.

Everything else is allowed (exit 0). Any parsing problem also allows the write, so this
hook can never break the workflow; it only blocks on a clear match.

Escape hatch: a write containing the text `language-guard: allow` skips the word check
(for example an LLM prompt that must list the words it is told to avoid).

Exempt from the word check: docs, steering, specs, tests, and the constants file that
defines the list. Keep the list in sync with .kiro/steering/product.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BANNED_WORDS = (
    "overcharged",
    "illegal",
    "fraud",
    "incorrect charge",
    "you should dispute",
    "you are owed",
)

PATH_KEYS = {"path", "file_path", "filepath", "targetfile", "file"}
EXEMPT_PREFIXES = (".kiro/", "docs/", "tests/", "pipeline/tests/", "private/", ".venv/", "node_modules/")
EXEMPT_FILES = {"core/constants.py", ".kiro/hooks/guard_language.py"}
ALLOW_MARKER = "language-guard: allow"
GITIGNORE_KIRO = re.compile(r"/?\.kiro(/|/\*\*|/\*)?")


def walk(node, out_paths: list[str], out_text: list[str]) -> None:
    """Collect path-like values and all other strings from nested JSON."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key.lower() in PATH_KEYS:
                out_paths.append(value)
            else:
                walk(value, out_paths, out_text)
    elif isinstance(node, list):
        for value in node:
            walk(value, out_paths, out_text)
    elif isinstance(node, str):
        out_text.append(node)


def relative(path: str) -> str:
    """Path relative to the repo root, with forward slashes."""
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(ROOT)
        except (ValueError, OSError):
            return p.as_posix()  # outside the repo: leave as is
    text = p.as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def is_exempt(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (
        rel in EXEMPT_FILES
        or rel.startswith(EXEMPT_PREFIXES)
        or name.startswith("test_")
        or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # not JSON we understand: allow

    paths: list[str] = []
    texts: list[str] = []
    walk(payload, paths, texts)
    if not paths:
        return 0  # cannot tell which file is written: allow

    rels = [relative(p) for p in paths]
    joined = "\n".join(texts)

    for rel in rels:
        if rel.rsplit("/", 1)[-1] == ".gitignore":
            for line in joined.splitlines():
                if GITIGNORE_KIRO.fullmatch(line.strip()):
                    print(
                        f"Blocked: {rel} would ignore .kiro. Steering, specs and hooks are "
                        "tracked on purpose (project rule).",
                        file=sys.stderr,
                    )
                    return 2

    if ALLOW_MARKER in joined:
        return 0
    if all(is_exempt(rel) for rel in rels):
        return 0

    lowered = joined.lower()
    hits = sorted({word for word in BANNED_WORDS if word in lowered})
    if hits:
        print(
            f"Blocked write to {', '.join(rels)}: contains banned wording {hits}. "
            "Use 'may be worth asking about' and give the reason. "
            f"(If this is an LLM prompt that must list the words, add '{ALLOW_MARKER}'.)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

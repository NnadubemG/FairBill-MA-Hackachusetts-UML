"""Tests for the .env loader. Fake values only; temporary files only; no network."""

from __future__ import annotations

import subprocess
from pathlib import Path

from backend.envfile import REPO_ROOT, describe_secret, load_env, parse_env

FAKE = "fake-value-123"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_sets_missing_variables(tmp_path):
    env: dict[str, str] = {}
    names = load_env(_write(tmp_path, f"ANTHROPIC_API_KEY={FAKE}\nEXTRACT_MODEL_ID=m1\n"), environ=env)
    assert env == {"ANTHROPIC_API_KEY": FAKE, "EXTRACT_MODEL_ID": "m1"}
    assert names == ["ANTHROPIC_API_KEY", "EXTRACT_MODEL_ID"]


def test_real_environment_wins(tmp_path):
    env = {"EXTRACT_MODEL_ID": "from-shell"}
    names = load_env(_write(tmp_path, "EXTRACT_MODEL_ID=from-file\nLETTER_MODEL_ID=l1\n"), environ=env)
    assert env["EXTRACT_MODEL_ID"] == "from-shell"
    assert env["LETTER_MODEL_ID"] == "l1"
    assert names == ["LETTER_MODEL_ID"]


def test_blank_existing_value_counts_as_not_set(tmp_path):
    env = {"EXPLAIN_MODEL_ID": "  "}
    load_env(_write(tmp_path, "EXPLAIN_MODEL_ID=e1\n"), environ=env)
    assert env["EXPLAIN_MODEL_ID"] == "e1"


def test_missing_file_is_fine(tmp_path):
    env: dict[str, str] = {}
    assert load_env(tmp_path / "nope.env", environ=env) == []
    assert env == {}


def test_directory_or_binary_file_is_fine(tmp_path):
    env: dict[str, str] = {}
    assert load_env(tmp_path, environ=env) == []
    bad = tmp_path / "bin.env"
    bad.write_bytes(b"\xff\xfe\x00\x80")
    assert load_env(bad, environ=env) == []
    assert env == {}


def test_empty_values_in_example_style_file_set_nothing(tmp_path):
    env: dict[str, str] = {}
    load_env(_write(tmp_path, "ANTHROPIC_API_KEY=\nEXTRACT_MODEL_ID=\n"), environ=env)
    assert env == {}


def test_parse_formats():
    text = (
        "# comment\n"
        "\n"
        "export A=1\n"
        'B="two words"\n'
        "C='single'\n"
        "D=plain # trailing comment\n"
        "E=has#hash\n"
        "bad line\n"
        "1BAD=x\n"
        'F="unclosed\n'
        "G = spaced \n"
    )
    assert parse_env(text) == {
        "A": "1",
        "B": "two words",
        "C": "single",
        "D": "plain",
        "E": "has#hash",
        "G": "spaced",
    }


def test_returns_names_never_values(tmp_path):
    names = load_env(_write(tmp_path, f"ANTHROPIC_API_KEY={FAKE}\n"), environ={})
    assert names == ["ANTHROPIC_API_KEY"]
    assert FAKE not in repr(names)


def test_loader_prints_and_logs_nothing(tmp_path, capsys, caplog):
    load_env(_write(tmp_path, f"ANTHROPIC_API_KEY={FAKE}\n"), environ={})
    load_env(tmp_path / "missing.env", environ={})
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert FAKE not in caplog.text


def test_loader_writes_no_files(tmp_path):
    path = _write(tmp_path, f"ANTHROPIC_API_KEY={FAKE}\n")
    before = sorted(p.name for p in tmp_path.iterdir())
    load_env(path, environ={})
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_env_example_has_the_four_names_and_no_values():
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    pairs = dict(
        line.split("=", 1) for line in lines if line.strip() and not line.lstrip().startswith("#")
    )
    assert set(pairs) == {"ANTHROPIC_API_KEY", "EXTRACT_MODEL_ID", "EXPLAIN_MODEL_ID", "LETTER_MODEL_ID"}
    assert all(value.strip() == "" for value in pairs.values())
    assert parse_env("\n".join(lines)) == {}


def test_git_ignores_env_but_not_the_example():
    def ignored(name: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "-q", name], cwd=REPO_ROOT, capture_output=True, check=False
        )
        return result.returncode == 0

    assert ignored(".env")
    assert not ignored(".env.example")


def test_describe_secret_shows_only_length_and_last_four():
    secret = "abcdefghij-0123456789-WXYZ"
    text = describe_secret(secret)
    assert text == f"length {len(secret)}, ends with ...WXYZ"
    assert secret not in text and secret[:-4] not in text


def test_describe_secret_hides_short_and_empty_values():
    assert describe_secret(None) == "not set"
    assert describe_secret("   ") == "not set"
    short = "short-key"
    assert describe_secret(short) == "length 9 (too short to show any characters)"
    assert short[-4:] not in describe_secret(short)


def test_shell_key_wins_over_env_file(tmp_path):
    env = {"ANTHROPIC_API_KEY": "from-shell-0000"}
    load_env(_write(tmp_path, "ANTHROPIC_API_KEY=from-file-1111\n"), environ=env)
    assert env["ANTHROPIC_API_KEY"] == "from-shell-0000"

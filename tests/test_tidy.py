"""Tests for gaeil-tidy, including Joshua's three sample note files."""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from gaeil_tidy.cli import main
from gaeil_tidy.tidy import tidy
from gaeil_tidy.translate import compile_gaeil, translate

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "examples" / "notes"
COAX = NOTES / "coax.gaeil"
DRAFT = NOTES / "draft-first.gaeil"
AIR = NOTES / "air-filters.gaeil"


def _run_gaeil(source: str, capsys=None) -> str:
    py = translate(source)
    compile_gaeil(source)
    buf = io.StringIO()
    # Execute with print going to our buffer.
    exec(compile(py, "<gaeil>", "exec"), {"__name__": "__main__", "print": lambda *a, **k: print(*a, file=buf, **k)})
    return buf.getvalue()


def test_keyword_normalization():
    result = tidy("Feidhm foo(n):\n    Fill n\n")
    assert "feidhm foo(n):" in result.source
    assert "fill n" in result.source
    assert any("Feidhm → feidhm" in c for c in result.changes)
    assert any("Fill → fill" in c for c in result.changes)
    compile_gaeil(result.source)


def test_english_keywords_become_irish():
    src = "def foo(n):\n    if n:\n        return True\n    else:\n        return False\n"
    result = tidy(src)
    assert "feidhm foo(n):" in result.source
    assert "má n:" in result.source
    assert "fill fíor" in result.source
    assert "eile:" in result.source
    assert "fill bréag" in result.source
    compile_gaeil(result.source)


def test_true_false_none_and_logic():
    result = tidy("x = True and not False or None\n")
    assert "fíor" in result.source
    assert "agus" in result.source
    assert "ní" in result.source
    assert "bréag" in result.source
    assert "nó" in result.source
    assert "neamhní" in result.source
    compile_gaeil(result.source)


def test_print_and_while_for():
    result = tidy("Print(1)\nwhile x:\n    for i in range(1):\n        pass\n")
    assert "scríobh(1)" in result.source
    assert "fad x:" in result.source
    assert "do i in range(1):" in result.source
    compile_gaeil(result.source)


def test_braces_become_indentation():
    result = tidy("feidhm foo(n) {\n    má n <= 0 {\n        fill 0\n    }\n    fill n\n}\n")
    compile_gaeil(result.source)
    assert "feidhm foo(n):" in result.source
    assert "má n <= 0:" in result.source
    assert "{" not in result.source
    assert "}" not in result.source
    assert _run_gaeil(result.source) == ""  # no print; just compiles/runs


def test_slash_comments_and_increments():
    result = tidy("i++\nj--\n// hello\n")
    assert "i += 1" in result.source
    assert "j -= 1" in result.source
    assert "# hello" in result.source
    assert "//" not in result.source
    compile_gaeil(result.source)


def test_trailing_semicolons_stripped():
    result = tidy("x = 1;\ny = 2;;\n")
    assert "x = 1" in result.source
    assert ";" not in result.source
    compile_gaeil(result.source)


def test_import_pytorch_noted():
    result = tidy("Import pytorch\nscríobh(1)\n")
    # unused import is commented so the file can run without torch
    assert "import torch" in result.source
    assert any("pytorch → torch" in c for c in result.changes)
    compile_gaeil(result.source)


def test_used_torch_import_kept():
    result = tidy("import pytorch\nx = torch.tensor\n")
    lines = [ln for ln in result.source.splitlines() if "import torch" in ln]
    assert lines
    assert not lines[0].lstrip().startswith("#")
    compile_gaeil(result.source)


def test_plain_english_becomes_comments():
    result = tidy("This draft uses the first\nCommand")
    assert result.source.lstrip().startswith("# This draft uses the first")
    assert "# Command" in result.source
    compile_gaeil(result.source)


def test_incomplete_import_is_todo_or_comment():
    result = tidy("Import\n")
    compile_gaeil(result.source)
    text = result.source
    assert "import" in text.lower()
    # The bare import cannot compile, so it is a comment or TODO.
    code_lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert code_lines == []


def test_clean_gaeil_still_runs():
    src = (
        "feidhm factorial(n):\n"
        "    má n <= 1:\n"
        "        fill 1\n"
        "    eile:\n"
        "        fill n * factorial(n - 1)\n"
        "\n"
        "scríobh(factorial(5))\n"
    )
    result = tidy(src)
    compile_gaeil(result.source)
    assert _run_gaeil(result.source).strip() == "120"


def test_noncompiling_line_becomes_todo():
    result = tidy("scríobh(1)\n@@@ not code\nscríobh(2)\n")
    compile_gaeil(result.source)
    assert any("GAEIL-TODO" in ln for ln in result.source.splitlines())
    assert result.todos
    assert _run_gaeil(result.source).strip().splitlines() == ["1", "2"]


def test_write_does_not_overwrite_original(tmp_path: Path):
    src = tmp_path / "notes.gaeil"
    src.write_text("scríobh(1)\n", encoding="utf-8")
    dest = tmp_path / "notes.tidy.gaeil"
    assert main([str(src), "--write"]) == 0
    assert src.read_text(encoding="utf-8") == "scríobh(1)\n"
    assert dest.exists()
    compile_gaeil(dest.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Joshua's three sample files
# ---------------------------------------------------------------------------

def test_sample_files_are_the_original_bytes():
    assert COAX.read_bytes() == (
        b'Import pytorch\nFeidhm \n{\nN, i++\n//Gravitas \nWorking //\n{\n'
        b'If n<=0 \n}\n}\n1/2z, ;n(""coax""), 1/2z\nPrint f \nFill =0'
    )
    assert DRAFT.read_bytes() == b"This draft uses the first\nCommand"
    assert AIR.read_bytes() == (
        b"Import\n\nCoax has to drive the air in a portal of potable air filters"
    )


@pytest.mark.parametrize("path", [COAX, DRAFT, AIR], ids=["coax", "draft", "air"])
def test_each_sample_tidies_and_compiles(path: Path):
    result = tidy(path.read_text(encoding="utf-8"))
    compile_gaeil(result.source)
    # And the written form would also compile.
    assert result.source.endswith("\n")


def test_draft_first_sample_is_comments_only():
    result = tidy(DRAFT.read_text(encoding="utf-8"))
    compile_gaeil(result.source)
    assert "# This draft uses the first" in result.source
    assert "# Command" in result.source
    code = [
        ln
        for ln in result.source.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert code == []
    assert _run_gaeil(result.source) == ""


def test_air_filters_sample_is_runnable_notes():
    result = tidy(AIR.read_text(encoding="utf-8"))
    compile_gaeil(result.source)
    assert "portal of potable air filters" in result.source
    # The English sentence is a comment; the bare Import does not stay live.
    live = [
        ln
        for ln in result.source.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert live == []
    assert _run_gaeil(result.source) == ""


def test_coax_sample_matches_agreed_shape_and_prints_5():
    result = tidy(COAX.read_text(encoding="utf-8"))
    compile_gaeil(result.source)
    src = result.source
    assert "feidhm coax(n):" in src
    assert "# Gravitas" in src
    assert "má n <= 0:" in src
    assert "fill 0" in src
    assert "fill n / 2" in src
    assert "scríobh(coax(10))" in src
    # Braces and C++ increments should be gone from live code.
    live = "\n".join(
        ln for ln in src.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    )
    assert "{" not in live and "}" not in live
    assert "++" not in live
    assert _run_gaeil(result.source).strip() == "5.0"
    # Recoveries and mechanical rewrites must be reported, not silent.
    report = result.report()
    assert "pytorch" in report
    assert "coax" in report
    assert "1/2z" in report or "n / 2" in report


def test_cli_stdout_is_tidied_source(tmp_path: Path, capsys):
    # Use a tiny clean-ish snippet so we can compare stdout.
    src = tmp_path / "hello.gaeil"
    src.write_text("Print(1)\n", encoding="utf-8")
    assert main([str(src)]) == 0
    out, err = capsys.readouterr()
    assert "scríobh(1)" in out
    assert "Tidy report" in err
    compile_gaeil(out)


def test_cli_run_executes_coax_sample(capsys):
    assert main([str(COAX), "--run"]) == 0
    out, err = capsys.readouterr()
    assert "feidhm coax(n):" in out
    assert "--- Output ---" in err
    assert "5.0" in err
    compile_gaeil(out)


def test_module_entrypoint():
    proc = subprocess.run(
        [sys.executable, "-m", "gaeil_tidy", str(DRAFT)],
        cwd=ROOT,
        env={**dict(**{**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "# This draft uses the first" in proc.stdout
    assert "Tidy report" in proc.stderr

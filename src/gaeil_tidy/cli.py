"""Command-line interface for gaeil-tidy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gaeil_tidy import __version__
from gaeil_tidy.tidy import tidy
from gaeil_tidy.translate import translate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gaeil-tidy",
        description=(
            "Turn rough, mixed-style notes into runnable Gaeil "
            "(Irish-language Python). Prints a change report on stderr."
        ),
    )
    parser.add_argument(
        "file",
        help="Path to a .gaeil file (or any text file of rough notes)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write tidied source to FILE.tidy.gaeil (never overwrites FILE)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the tidied Gaeil after translating it to Python",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"gaeil-tidy {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = Path(args.file)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as err:
        print(f"gaeil-tidy: cannot read {path}: {err}", file=sys.stderr)
        return 1

    result = tidy(source)
    sys.stderr.write(result.report())
    if result.todos:
        sys.stderr.write(
            "Lines marked # GAEIL-TODO: were left as comments so the file runs.\n"
        )

    if args.write:
        dest = path.with_name(path.stem + ".tidy.gaeil")
        dest.write_text(result.source, encoding="utf-8")
        sys.stderr.write(f"Wrote {dest}\n")
    else:
        sys.stdout.write(result.source)
        if result.source and not result.source.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    if args.run:
        sys.stderr.write("--- Output ---\n")
        py_code = translate(result.source)
        old_stdout = sys.stdout
        try:
            sys.stdout = sys.stderr
            exec(compile(py_code, str(path), "exec"), {"__name__": "__main__"})
        except SystemExit as err:
            return int(err.code or 0)
        except Exception as err:  # noqa: BLE001 — surface runtime errors to the user
            sys.stdout = old_stdout
            print(f"gaeil-tidy: ran tidied code but it failed: {err}", file=sys.stderr)
            return 1
        finally:
            sys.stdout = old_stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())

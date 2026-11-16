"""Gaeil-to-Python translator.

Mirrors https://github.com/fitzyracing1/Gaeil/blob/main/gaeil.py so tidied
notes can be compile-checked and optionally run without a second package.
"""

from __future__ import annotations

import re

from gaeil_tidy.keywords import IRISH_TO_PYTHON


def translate(source: str) -> str:
    """Replace Irish Gaeil keywords with Python, leaving other text as is."""
    code = source
    for irish, python in IRISH_TO_PYTHON.items():
        code = re.sub(rf"\b{re.escape(irish)}\b", python, code, flags=re.UNICODE)
    return code


def compile_gaeil(source: str, filename: str = "<gaeil>"):
    """Translate to Python and compile. Raises SyntaxError on failure."""
    return compile(translate(source), filename, "exec")

"""Gaeil keyword maps.

Copied from the Gaeil translator at https://github.com/fitzyracing1/Gaeil
(gaeil.py) so this helper can run as a standalone project. Irish keywords
are the canonical form this tidier writes; English synonyms are accepted
in rough notes and converted to Irish.
"""

from __future__ import annotations

# Irish keyword -> Python, same mapping as fitzyracing1/Gaeil gaeil.py.
IRISH_TO_PYTHON: dict[str, str] = {
    "scríobh": "print",
    "má": "if",
    "eile": "else",
    "fad": "while",
    "do": "for",
    "feidhm": "def",
    "fill": "return",
    "fíor": "True",
    "bréag": "False",
    "agus": "and",
    "nó": "or",
    "ní": "not",
    "léigh": "input",
    "neamhní": "None",
}

# English (and Python) keywords accepted in rough notes -> canonical Gaeil.
ENGLISH_TO_GAEIL: dict[str, str] = {
    "print": "scríobh",
    "if": "má",
    "else": "eile",
    "while": "fad",
    "for": "do",
    "def": "feidhm",
    "return": "fill",
    "True": "fíor",
    "False": "bréag",
    "and": "agus",
    "or": "nó",
    "not": "ní",
    "input": "léigh",
    "None": "neamhní",
}

# Canonical lowercase Irish form for each Irish keyword (any case).
IRISH_CANONICAL: dict[str, str] = {word: word for word in IRISH_TO_PYTHON}

# Words that mean a line is "code-like" rather than English prose.
CODE_KEYWORDS: frozenset[str] = frozenset(
    {k.lower() for k in ENGLISH_TO_GAEIL}
    | {k.lower() for k in IRISH_TO_PYTHON}
    | {"import", "from", "class", "pass", "break", "continue", "in", "is"}
)

"""Rule-based tidier that turns rough notes into runnable Gaeil.

Every rewrite is recorded in a change report. Heuristics that recover a
function sketch (name, parameters, a half-value return, a demo call) are
also reported, never applied silently. Lines that still cannot compile are
kept as ``# GAEIL-TODO:`` comments so the result always runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gaeil_tidy.keywords import CODE_KEYWORDS, ENGLISH_TO_GAEIL, IRISH_CANONICAL
from gaeil_tidy.translate import compile_gaeil, translate

# Math shorthand "1/2z" (and close typo forms) seen in rough notes.
HALF_Z_RE = re.compile(r"1\s*/\s*2z\b", re.IGNORECASE)

# Doubled quotes around a name: ""coax""
DOUBLED_STRING_RE = re.compile(r'""([A-Za-z_][A-Za-z0-9_]*)""')

# Bare identifier (function or variable name).
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class TidyResult:
    """Tidied Gaeil source plus a report of every change and TODO line."""

    source: str
    changes: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = ["Tidy report"]
        lines.append("-----------")
        if self.changes:
            for item in self.changes:
                lines.append(f"- {item}")
        else:
            lines.append("- no changes")
        if self.todos:
            lines.append("TODO lines:")
            for item in self.todos:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"


def tidy(source: str) -> TidyResult:
    """Return runnable Gaeil for *source*, with a change/TODO report."""
    result = TidyResult(source=source)
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    if text != source.replace("\r\n", "\n") or "\r" in source:
        result.changes.append("normalized line endings to LF")

    text = _comment_prose_lines(text, result)
    text = _convert_slash_comments(text, result)
    text = _rewrite_increments(text, result)
    text = _strip_semicolons(text, result)
    text = _normalize_imports(text, result)
    text = _normalize_keywords(text, result)
    text = _space_operators(text, result)
    text = _convert_braces(text, result)
    text = _fix_fill_assignment(text, result)
    text = _normalize_doubled_quotes(text, result)
    text = _add_print_call_parens(text, result)
    text = _recover_function_sketch(text, result)
    text = _comment_unused_imports(text, result)
    text = _ensure_compiles(text, result)

    if text and not text.endswith("\n"):
        text += "\n"
    result.source = text
    return result


# ---------------------------------------------------------------------------
# Segment helper: apply a function only to code, not strings or # comments
# ---------------------------------------------------------------------------

def _map_code(line: str, fn) -> str:
    """Apply *fn* to code segments of a single line, leaving strings/comments."""
    parts: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "#":
            parts.append(line[i:])
            break
        if ch in "\"'":
            quote = ch
            j = i + 1
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if line[j] == quote:
                    j += 1
                    break
                j += 1
            parts.append(line[i:j])
            i = j
            continue
        j = i + 1
        while j < n and line[j] not in "\"'#":
            j += 1
        parts.append(fn(line[i:j]))
        i = j
    return "".join(parts)


def _code_prefix(line: str) -> str:
    """Return the code part of a line (before a # comment), minus strings kept."""
    out = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "#":
            break
        if ch in "\"'":
            quote = ch
            j = i + 1
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if line[j] == quote:
                    j += 1
                    break
                j += 1
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------

def _looks_like_code(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return True
    code = _code_prefix(stripped)
    if re.search(r"=\s*", code) and re.search(r"[<>=/*+\-]", code):
        return True
    if re.search(r"[(){}[\];]|\+\+|--|//|<=|>=|==|!=", code):
        return True
    if re.search(r"[<>=/*+\-%]", code):
        return True
    words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÀ-ÿ_]+", code, flags=re.UNICODE)
    for word in words:
        if word.lower() in CODE_KEYWORDS or word in ENGLISH_TO_GAEIL:
            return True
        # Irish keywords with accents, compared case-insensitively.
        if word.lower() in {k.lower() for k in IRISH_CANONICAL}:
            return True
    return False


def _looks_like_prose(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _looks_like_code(line):
        return False
    # Letters, spaces, and light punctuation only.
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÀ-ÿ][A-Za-zÁÉÍÓÚáéíóúÀ-ÿ0-9 ',.!?\-]*", stripped):
        return False
    words = stripped.split()
    if len(words) >= 2:
        return True
    # A single capitalized bare word is treated as a note, not a variable.
    return len(words) == 1 and words[0][:1].isupper() and words[0].isalpha()


def _comment_prose_lines(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    out = []
    for line in lines:
        if _looks_like_prose(line):
            indent = line[: len(line) - len(line.lstrip())]
            body = line.strip()
            out.append(f"{indent}# {body}")
            result.changes.append(f"commented English prose: {body}")
        else:
            out.append(line)
    return "\n".join(out)


def _convert_slash_comments(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    out = []
    changed = False
    for line in lines:
        if "//" not in line:
            out.append(line)
            continue

        def replace_slashes(code: str) -> str:
            # Do not treat the // in URLs (://) as a comment.
            # Always put a space after # so "//Gravitas" becomes "# Gravitas".
            return re.sub(r"(?<!:)//\s*", "# ", code)

        # Split so we only look for // outside strings.
        new_line = _map_code(line, replace_slashes)
        if new_line != line:
            changed = True
        # "Working //" or "Working #" where the code is just a note.
        code = _code_prefix(new_line).strip()
        comment_m = re.search(r"#(.*)$", new_line)
        if code and _looks_like_prose(code) and (comment_m is None or not comment_m.group(1).strip()):
            indent = new_line[: len(new_line) - len(new_line.lstrip())]
            new_line = f"{indent}# {code}"
            changed = True
        out.append(new_line)
    if changed:
        result.changes.append("converted // comments to #")
    return "\n".join(out)


def _rewrite_increments(text: str, result: TidyResult) -> str:
    found_inc = False
    found_dec = False

    def repl(code: str) -> str:
        nonlocal found_inc, found_dec

        def inc(m: re.Match[str]) -> str:
            nonlocal found_inc
            found_inc = True
            return f"{m.group(1)} += 1"

        def dec(m: re.Match[str]) -> str:
            nonlocal found_dec
            found_dec = True
            return f"{m.group(1)} -= 1"

        code = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\+\+", inc, code)
        code = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)--", dec, code)
        return code

    lines = [_map_code(line, repl) for line in text.splitlines()]
    if found_inc:
        result.changes.append("rewrote i++-style increments to i += 1")
    if found_dec:
        result.changes.append("rewrote i-- style decrements to i -= 1")
    return "\n".join(lines)


def _strip_semicolons(text: str, result: TidyResult) -> str:
    changed = False

    def repl(code: str) -> str:
        nonlocal changed
        new = re.sub(r";+\s*$", "", code)
        # Leading or leftover mid-list semicolons: ";n(" or ", ;n("
        new2 = re.sub(r";\s*", "", new)
        if new2 != code:
            changed = True
        return new2

    lines = [_map_code(line, repl) for line in text.splitlines()]
    if changed:
        result.changes.append("stripped leftover semicolons")
    return "\n".join(lines)


def _normalize_imports(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    out = []
    for line in lines:
        raw = line
        m = re.match(r"^(\s*)(import)\b(.*)$", line, flags=re.IGNORECASE)
        if m:
            indent, _, rest = m.group(1), m.group(2), m.group(3)
            note = ""
            new_rest = rest
            # pytorch is imported as torch.
            def torch_name(mm: re.Match[str]) -> str:
                return mm.group(0).replace(mm.group(1), "torch")

            new_rest, n_torch = re.subn(
                r"\b(pytorch)\b", torch_name, rest, flags=re.IGNORECASE
            )
            new_line = f"{indent}import{new_rest}"
            if new_line != raw or line.lstrip()[:6].lower() == "import" and line.lstrip()[:6] != "import":
                if line.lstrip()[:6].lower() != "import" or line.lstrip()[:6] != "import":
                    result.changes.append("Import → import")
            if n_torch:
                result.changes.append(
                    "pytorch → torch (PyTorch's import name is torch)"
                )
            out.append(new_line)
            continue
        # from pytorch import ...
        m = re.match(r"^(\s*)(from)\b(.*)$", line, flags=re.IGNORECASE)
        if m:
            indent, _, rest = m.group(1), m.group(2), m.group(3)
            new_rest, n_torch = re.subn(r"\bpytorch\b", "torch", rest, flags=re.IGNORECASE)
            new_line = f"{indent}from{new_rest}"
            if line.lstrip()[:4] != "from":
                result.changes.append("From → from")
            if n_torch:
                result.changes.append(
                    "pytorch → torch (PyTorch's import name is torch)"
                )
            out.append(new_line)
            continue
        out.append(line)
    return "\n".join(out)


def _keyword_replacer(code: str, changed: list[str]) -> str:
    # Build one regex of all English and Irish keywords, longest first.
    words = sorted(
        set(ENGLISH_TO_GAEIL) | set(IRISH_CANONICAL),
        key=len,
        reverse=True,
    )
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in words) + r")\b",
        flags=re.IGNORECASE | re.UNICODE,
    )
    # Lookup is case-insensitive.
    table: dict[str, str] = {}
    for eng, irish in ENGLISH_TO_GAEIL.items():
        table[eng.lower()] = irish
    for irish in IRISH_CANONICAL:
        table[irish.lower()] = irish

    def repl(m: re.Match[str]) -> str:
        token = m.group(0)
        canon = table.get(token.lower())
        if canon is None:
            return token
        if token != canon:
            changed.append(f"{token} → {canon}")
        return canon

    return pattern.sub(repl, code)


def _normalize_keywords(text: str, result: TidyResult) -> str:
    seen: list[str] = []
    out = []
    for line in text.splitlines():
        out.append(_map_code(line, lambda c, s=seen: _keyword_replacer(c, s)))
    # Deduplicate report lines but keep order.
    reported = set()
    for item in seen:
        if item not in reported:
            result.changes.append(item)
            reported.add(item)
    return "\n".join(out)


def _space_operators(text: str, result: TidyResult) -> str:
    changed = False

    def repl(code: str) -> str:
        nonlocal changed
        new = code
        for op in ("<=", ">=", "==", "!=", "+=", "-=", "*=", "/="):
            new = re.sub(rf"\s*{re.escape(op)}\s*", f" {op} ", new)
        # Lone < > = * / + - (after the compounds above are already spaced).
        new = re.sub(r"\s*<=\s*", " <= ", new)  # already done
        new = re.sub(r"(?<![<>=!+\-*/])=(?!=)", " = ", new)
        new = re.sub(r"(?<![<>=!])<(?!=)", " < ", new)
        new = re.sub(r"(?<![<>=!])>(?!=)", " > ", new)
        new = re.sub(r" +", " ", new)
        new = new.strip() if code.strip() != code else new
        # Preserve leading/trailing whitespace of the code segment except
        # collapsed internals. Re-apply original end padding later at line level.
        if new != code and new.replace(" ", "") == code.replace(" ", ""):
            # Only spacing changed; keep it. Compare without all spaces?
            pass
        if re.sub(r"\s+", "", new) == re.sub(r"\s+", "", code) and new != code:
            changed = True
        return new

    out = []
    for line in text.splitlines():
        leading = line[: len(line) - len(line.lstrip())] if line.strip() else line
        if not line.strip():
            out.append(line)
            continue
        body = line[len(leading) :]
        # Don't touch comment-only lines.
        if body.lstrip().startswith("#"):
            out.append(line)
            continue
        new_body = _map_code(body, repl)
        new_body = new_body.rstrip()
        # Restore a single trailing space? No, strip trailing spaces in code.
        out.append(leading + new_body)
    if changed:
        result.changes.append("added spaces around operators")
    return "\n".join(out)


def _looks_like_header(line: str) -> bool:
    """True if a line is a block header (feidhm/má/if/for/...) rather than a statement."""
    code = _code_prefix(line).strip()
    if not code:
        return False
    return bool(
        re.match(
            r"^(feidhm|má|eile|fad|do|def|if|else|elif|while|for|"
            r"try|except|finally|class|with|async)\b",
            code,
        )
    )


def _previous_header_line(buf: str, lines: list[str]) -> bool:
    if buf.strip() and not buf.strip().startswith("#"):
        return _looks_like_header(buf)
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].strip() or lines[i].lstrip().startswith("#"):
            continue
        return _looks_like_header(lines[i])
    return False


def _header_follows_brace(tokens: list[tuple[str, str]], index: int) -> bool:
    """True if the next non-empty, non-comment text after tokens[index] ({) is a header.

    Covers the messy style where a '{' sits on the line *before* `If n<=0`.
    """
    buf = ""
    for kind, val in tokens[index + 1 :]:
        if kind == "LBRACE" or kind == "RBRACE":
            return False
        if kind == "TEXT":
            buf += val
            continue
        if kind == "NL":
            piece = buf.strip()
            buf = ""
            if not piece or piece.startswith("#"):
                continue
            return _looks_like_header(piece)
    piece = buf.strip()
    return bool(piece) and not piece.startswith("#") and _looks_like_header(piece)


def _add_colon(text: str) -> str:
    if not text.strip() or text.lstrip().startswith("#"):
        return text
    if _code_prefix(text).rstrip().endswith(":"):
        return text
    if "#" in text:
        # Only split on a comment marker outside strings via _code_prefix length.
        code = _code_prefix(text)
        return code.rstrip() + ":" + text[len(code) :]
    return text.rstrip() + ":"


def _convert_braces(text: str, result: TidyResult) -> str:
    if not _source_has_brace(text):
        return text

    # Tokenize into NEWLINE, LBRACE, RBRACE, TEXT (which may include spaces).
    tokens: list[tuple[str, str]] = []
    for line in text.splitlines():
        tokens.extend(_split_braces_line(line))
        tokens.append(("NL", "\n"))

    indent = 0
    buf = ""
    lines: list[str] = []
    pending_header_brace = False

    def flush(force_empty: bool = False) -> None:
        nonlocal buf, indent, pending_header_brace
        if buf == "" and not force_empty:
            return
        stripped = buf.strip()
        if pending_header_brace and stripped and not stripped.startswith("#"):
            buf = _add_colon(buf)
            stripped = buf.strip()
            prefix = "    " * indent
            if stripped:
                lines.append(prefix + stripped)
            else:
                lines.append("")
            buf = ""
            indent += 1
            pending_header_brace = False
            return
        prefix = "    " * indent
        if stripped:
            lines.append(prefix + stripped)
        else:
            lines.append("")
        buf = ""

    def colonize_previous() -> None:
        nonlocal buf
        if buf.strip() and not buf.strip().startswith("#"):
            buf = _add_colon(buf)
            return
        for i in range(len(lines) - 1, -1, -1):
            if not lines[i].strip() or lines[i].lstrip().startswith("#"):
                continue
            lines[i] = _add_colon(lines[i])
            return

    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "TEXT":
            buf += val
        elif kind == "LBRACE":
            # If the current/previous line is already a header, the brace belongs
            # to it. If a header follows this brace, wait and attach it there
            # instead of colonizing a leftover statement such as `N, i += 1`.
            if _previous_header_line(buf, lines):
                colonize_previous()
                flush()
                indent += 1
            elif _header_follows_brace(tokens, i):
                flush()
                pending_header_brace = True
            else:
                flush()
                indent += 1
        elif kind == "RBRACE":
            flush()
            indent = max(0, indent - 1)
        elif kind == "NL":
            flush()
        i += 1
    flush()

    result.changes.append("converted { } braces to colons and indentation")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _source_has_brace(text: str) -> bool:
    for line in text.splitlines():
        if "{" in _code_prefix(line) or "}" in _code_prefix(line):
            return True
    return False


def _split_braces_line(line: str) -> list[tuple[str, str]]:
    """Split a line into TEXT / LBRACE / RBRACE, ignoring braces in strings/#."""
    tokens: list[tuple[str, str]] = []
    buf: list[str] = []
    i = 0
    n = len(line)
    in_string = False
    quote = ""
    in_comment = False
    while i < n:
        ch = line[i]
        if in_comment:
            buf.append(ch)
            i += 1
            continue
        if in_string:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                buf.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                in_string = False
            i += 1
            continue
        if ch == "#":
            in_comment = True
            buf.append(ch)
            i += 1
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "{":
            if buf:
                tokens.append(("TEXT", "".join(buf)))
                buf = []
            tokens.append(("LBRACE", "{"))
            i += 1
            continue
        if ch == "}":
            if buf:
                tokens.append(("TEXT", "".join(buf)))
                buf = []
            tokens.append(("RBRACE", "}"))
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        tokens.append(("TEXT", "".join(buf)))
    return tokens


def _fix_fill_assignment(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    out = []
    for line in lines:
        code = _code_prefix(line)
        comment = line[len(code) :] if len(line) > len(code) else ""
        m = re.match(r"^(\s*)fill\s*=\s*(\S.*)$", code)
        if m and "fill ==" not in code:
            new_code = f"{m.group(1)}fill {m.group(2).rstrip()}"
            out.append(new_code + comment)
            result.changes.append(
                f"fill = {m.group(2).strip()} → fill {m.group(2).strip()} "
                "(treated '=' as a return typo, not assignment)"
            )
        else:
            out.append(line)
    return "\n".join(out)


def _code_and_comment_split_line(line: str) -> tuple[str, str]:
    code = _code_prefix(line)
    return code, line[len(code) :]


def _normalize_doubled_quotes(text: str, result: TidyResult) -> str:
    if not DOUBLED_STRING_RE.search(text):
        return text

    def repl(code: str) -> str:
        return DOUBLED_STRING_RE.sub(r'"\1"', code)

    lines = [_map_code(line, repl) for line in text.splitlines()]
    result.changes.append('normalized doubled quotes ""name"" to "name"')
    return "\n".join(lines)


def _add_print_call_parens(text: str, result: TidyResult) -> str:
    """scríobh foo  ->  scríobh(foo); same for léigh."""
    changed = False
    pattern = re.compile(r"\b(scríobh|léigh)\b(?!\s*\()(\s+)(.+)$")

    def repl(code: str) -> str:
        nonlocal changed
        m = pattern.search(code)
        if not m:
            return code
        # Don't wrap if the rest is a comment-only leftover or empty.
        rest = m.group(3).strip()
        if not rest or rest.startswith("#"):
            return code
        changed = True
        start, end = m.span()
        return code[: m.start(2)] + "(" + rest + ")" + code[end:]

    lines = [_map_code(line, repl) for line in text.splitlines()]
    if changed:
        result.changes.append("added parentheses to scríobh/léigh calls")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Function-sketch recovery (reported heuristics)
# ---------------------------------------------------------------------------

_FEIDHM_HEAD = re.compile(r"^(\s*)feidhm\s*(?:([A-Za-z_][A-Za-z0-9_]*)\s*)?(?:\((.*?)\))?\s*:?\s*$")


def _recover_function_sketch(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    # Find an anonymous or incomplete `feidhm` header.
    header_idx = None
    header_indent = 0
    existing_name = None
    existing_params = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = _FEIDHM_HEAD.match(line)
        if m:
            header_idx = i
            header_indent = len(m.group(1))
            existing_name = m.group(2)
            params_raw = m.group(3)
            if params_raw is not None:
                existing_params = [p.strip() for p in params_raw.split(",") if p.strip()]
            break
    if header_idx is None:
        return text

    # Body: following lines indented more than the header, plus (for a
    # just-closed brace sketch) a short run of leftover module-level lines
    # that look like they belong to the function (returns, 1/2z, n("name")).
    body_idx = []
    trail_idx = []
    i = header_idx + 1
    while i < len(lines):
        if not lines[i].strip():
            body_idx.append(i)
            i += 1
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        if indent > header_indent:
            body_idx.append(i)
            i += 1
            continue
        break
    # Trailing leftovers immediately after the body, until a blank or a
    # clearly-separate statement like scríobh / a new feidhm.
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            break
        if raw.lstrip().startswith("feidhm"):
            break
        if re.match(r"^\s*scríobh\b", raw):
            trail_idx.append(i)
            i += 1
            continue
        if _looks_like_orphan(raw):
            trail_idx.append(i)
            i += 1
            continue
        break

    body_lines = [lines[j] for j in body_idx]
    trail_lines = [lines[j] for j in trail_idx]
    pool = body_lines + trail_lines
    pool_text = "\n".join(pool)

    name = existing_name
    found_names = [
        m.group(1)
        for m in re.finditer(r'["\']([A-Za-z_][A-Za-z0-9_]*)["\']', pool_text)
    ]
    if name is None and found_names:
        name = found_names[0]
        result.changes.append(
            f'recovered function name {name!r} from a string in the notes'
        )

    params = list(existing_params or [])
    if not params:
        # Parameter used in a má/fad/do condition, or a bare leading ident.
        cond = re.search(r"\b(?:má|fad|do)\s+([A-Za-z_][A-Za-z0-9_]*)\b", pool_text)
        if cond:
            params = [cond.group(1)]
            result.changes.append(
                f"recovered parameter {params[0]!r} from a condition"
            )
        else:
            ident_m = re.search(
                r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,",
                "\n".join(body_lines),
                re.MULTILINE,
            )
            if ident_m:
                params = [ident_m.group(1)]
                result.changes.append(
                    f"recovered parameter {params[0]!r} from the function body"
                )

    # If the header was already complete and there are no orphans to fold in,
    # leave the function alone (aside from earlier mechanical passes).
    header_incomplete = not existing_name or existing_params is None
    if not header_incomplete and not any(_looks_like_orphan(t) for t in trail_lines):
        return text
    if name is None:
        # Cannot recover a name; leave for the compile-TODO pass.
        return text

    param_sig = ", ".join(params)
    new_header = f"{' ' * header_indent}feidhm {name}({param_sig}):"
    if lines[header_idx] != new_header:
        result.changes.append(
            f"completed function header: {lines[header_idx].strip()!r} → {new_header.strip()!r}"
        )

    # Rebuild the body: drop leftover increment sketches, fold orphans in,
    # interpret 1/2z, attach fill to an empty má block.
    new_body: list[str] = []
    body_indent = " " * (header_indent + 4)

    def relabel(line: str, dest_indent: str) -> str:
        return dest_indent + line.lstrip() if line.strip() else line

    # First, process original indented body.
    skip_body = set()
    for j, raw in zip(body_idx, body_lines):
        stripped = raw.strip()
        if _is_increment_leftover(stripped):
            result.changes.append(
                f"dropped leftover increment sketch {stripped!r} "
                "(not a valid statement in the reconstructed function)"
            )
            skip_body.add(j)
            continue
        new_body.append(raw)

    # Interpret trail orphans and fold them into the body, except scríobh
    # demo calls which stay at module level after the function.
    module_after: list[str] = []
    pending_fill: str | None = None
    pending_half: str | None = None

    for raw in trail_lines:
        stripped = raw.strip()
        if re.match(r"^scríobh\b", stripped):
            module_after.append(_maybe_demo_call(stripped, name, result))
            continue
        if HALF_Z_RE.search(stripped) or _is_half_orphan(stripped):
            if params:
                pending_half = f"{body_indent}fill {params[0]} / 2"
                result.changes.append(
                    f"interpreted {stripped!r} as 'fill {params[0]} / 2' "
                    f"(half of parameter {params[0]}; shorthand 1/2z)"
                )
            else:
                pending_half = f"{body_indent}# GAEIL-TODO: {stripped} — cannot interpret 1/2z without a parameter"
            continue
        if re.match(r"^fill\b", stripped):
            pending_fill = f"{body_indent}{stripped}"
            result.changes.append(
                f"moved {stripped!r} into the function body"
            )
            continue
        if _is_increment_leftover(stripped):
            result.changes.append(
                f"dropped leftover increment sketch {stripped!r}"
            )
            continue
        # Other orphans: keep in the body if they look like statements,
        # otherwise leave a TODO in the body.
        new_body.append(body_indent + stripped)

    # Attach a pending fill to an empty má/fad block if there is one.
    new_body = _fill_empty_blocks(new_body, pending_fill, result)
    pending_used = _body_contains(new_body, pending_fill) if pending_fill else False
    if pending_fill and not pending_used:
        # No empty block to attach to: append at the start or end of body.
        # Prefer just after comments at the top? Append before a final return.
        new_body.append(pending_fill)

    if pending_half:
        new_body.append(pending_half)

    # Drop blank lines at start/end of body, keep internal blanks and comments.
    while new_body and not new_body[0].strip():
        new_body.pop(0)
    while new_body and not new_body[-1].strip():
        new_body.pop()

    # Reassemble: lines before header, new header, body, then remaining
    # module lines with trail orphans removed (replaced by module_after).
    skip = set(trail_idx) | skip_body
    rebuilt: list[str] = []
    for i, line in enumerate(lines):
        if i == header_idx:
            rebuilt.append(new_header)
            rebuilt.extend(new_body)
            continue
        if i in skip or i in body_idx:
            continue
        rebuilt.append(line)
    # Place demo calls immediately after the function (before later lines
    # already appended). Because we skipped trail_idx, module_after needs
    # to be inserted after the function. Find the insert point: after the
    # last body line we just added, i.e. right after new_header+new_body,
    # which is already the current end of the function in `rebuilt` at the
    # moment we processed the header. Lines after the trail were appended
    # later in the loop, so we need a cleaner rebuild.

    # Cleaner rebuild:
    before = lines[:header_idx]
    after_idx = trail_idx[-1] + 1 if trail_idx else (
        body_idx[-1] + 1 if body_idx else header_idx + 1
    )
    after = [line for i, line in enumerate(lines[after_idx:], start=after_idx) if i not in skip]
    rebuilt = before + [new_header] + new_body + module_after + after
    return "\n".join(rebuilt)


def _looks_like_orphan(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^fill\b", stripped):
        return True
    if HALF_Z_RE.search(stripped) or _is_half_orphan(stripped):
        return True
    if re.match(r"^scríobh\b", stripped):
        return True
    if _is_increment_leftover(stripped):
        return True
    if re.search(r'["\'][A-Za-z_][A-Za-z0-9_]*["\']', stripped) and "(" in stripped:
        return True
    return False


def _is_half_orphan(line: str) -> bool:
    return bool(HALF_Z_RE.search(line))


def _is_increment_leftover(stripped: str) -> bool:
    # "n, i += 1" or "N, i += 1:" sitting alone as a C-style for-loop leftover.
    cleaned = stripped.rstrip(":").strip()
    return bool(
        re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s*\+=\s*1",
            cleaned,
        )
    )


def _maybe_demo_call(stripped: str, func_name: str, result: TidyResult) -> str:
    """Rewrite 'scríobh(f)' / 'scríobh f' into a demo call if f is a stub."""
    m = re.match(r"^scríobh\s*(?:\((.*)\)|(.*))$", stripped)
    if not m:
        return stripped
    arg = (m.group(1) if m.group(1) is not None else m.group(2) or "").strip()
    if arg in {"", "f", "F", "func", "function"}:
        call = f"scríobh({func_name}(10))"
        result.changes.append(
            f"rewrote {stripped!r} to a demo call {call} "
            "(argument 10 is a placeholder so the file runs)"
        )
        return call
    return stripped if stripped.startswith("scríobh(") else f"scríobh({arg})"


def _fill_empty_blocks(
    body: list[str], pending_fill: str | None, result: TidyResult
) -> list[str]:
    if not pending_fill:
        return body
    fill_stripped = pending_fill.strip()
    out: list[str] = []
    i = 0
    used = False
    while i < len(body):
        line = body[i]
        out.append(line)
        if re.match(r"^\s*(má|eile|fad|do)\b.*:\s*$", _code_prefix(line).rstrip()):
            block_indent = len(line) - len(line.lstrip())
            j = i + 1
            only_blank_or_comment = True
            while j < len(body):
                nxt = body[j]
                if not nxt.strip():
                    j += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= block_indent:
                    break
                if not nxt.lstrip().startswith("#"):
                    only_blank_or_comment = False
                    break
                j += 1
            if only_blank_or_comment and not used:
                inner = " " * (block_indent + 4) + fill_stripped
                out.append(inner)
                result.changes.append(
                    f"placed {fill_stripped!r} in the empty block under {line.strip()!r}"
                )
                used = True
        i += 1
    return out


def _body_contains(body: list[str], line: str | None) -> bool:
    if not line:
        return False
    target = line.strip()
    return any(existing.strip() == target for existing in body)


# ---------------------------------------------------------------------------
# Unused imports and compile safety net
# ---------------------------------------------------------------------------

def _comment_unused_imports(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    # Collect imported names vs. uses in the rest of the (comment-stripped) code.
    imported: list[tuple[int, str, str]] = []  # idx, module, original line
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)import\s+(\S+)", line)
        if m:
            module = m.group(2).split("as")[0].strip().split(".")[0]
            imported.append((i, module, line))
    if not imported:
        return text

    # Remaining code text with those import lines removed, comments stripped.
    other_parts = []
    import_idxs = {i for i, _, _ in imported}
    for i, line in enumerate(lines):
        if i in import_idxs:
            continue
        other_parts.append(_code_prefix(line))
    other = "\n".join(other_parts)

    out = list(lines)
    for i, module, line in imported:
        # A module is used if its name appears as a word in other code.
        if re.search(rf"\b{re.escape(module)}\b", other):
            continue
        indent = line[: len(line) - len(line.lstrip())]
        out[i] = f"{indent}# {line.strip()}"
        result.changes.append(
            f"commented unused {line.strip()!r} so the file runs without that package"
        )
    return "\n".join(out)


def _ensure_compiles(text: str, result: TidyResult) -> str:
    """Comment out lines that still fail compile(), and fill empty blocks."""
    text = _add_pass_to_empty_blocks(text, result)
    source = text
    max_iters = max(8, len(source.splitlines()) + 4)
    for _ in range(max_iters):
        err = _syntax_error(source)
        if err is None:
            return source
        source2 = _add_pass_to_empty_blocks(source, result)
        if source2 != source and _syntax_error(source2) is None:
            return source2
        source = source2
        lineno = err.lineno or 1
        lines = source.splitlines()
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            break
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            # Pointed at a blank line; try the previous non-empty line.
            found = False
            for k in range(idx - 1, -1, -1):
                if lines[k].strip() and not lines[k].lstrip().startswith("#"):
                    idx = k
                    line = lines[idx]
                    stripped = line.strip()
                    found = True
                    break
            if not found:
                break
        if stripped.startswith("# GAEIL-TODO:"):
            # Already marked; avoid a loop.
            break
        indent = line[: len(line) - len(line.lstrip())]
        reason = (err.msg or "does not compile").rstrip()
        lines[idx] = f"{indent}# GAEIL-TODO: {stripped} — {reason}"
        note = f"{stripped} — {reason}"
        result.changes.append(f"commented non-compiling line as GAEIL-TODO: {stripped}")
        result.todos.append(note)
        source = "\n".join(lines)
        if text.endswith("\n"):
            source += "\n"
        source = _add_pass_to_empty_blocks(source, result)
    return source


def _syntax_error(source: str) -> SyntaxError | None:
    try:
        compile_gaeil(source)
        return None
    except SyntaxError as err:
        return err


def _add_pass_to_empty_blocks(text: str, result: TidyResult) -> str:
    lines = text.splitlines()
    out: list[str] = []
    added = False
    for i, line in enumerate(lines):
        out.append(line)
        code = _code_prefix(line).rstrip()
        if re.search(r":\s*$", code) and not line.lstrip().startswith("#"):
            indent = len(line) - len(line.lstrip())
            j = i + 1
            has_body = False
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or nxt.lstrip().startswith("#"):
                    j += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= indent:
                    break
                has_body = True
                break
            if not has_body:
                # Comments-only or nothing: need a pass (or the comments stay
                # and pass follows them if we only look at the first non-blank).
                # If the next lines are comments at a deeper indent, put pass
                # after this header (before those comments is also fine).
                out.append(" " * (indent + 4) + "pass")
                added = True
    if added:
        # Only report once even if we run this more than once.
        if not any(c.startswith("added pass") for c in result.changes):
            result.changes.append("added pass to empty blocks")
        return "\n".join(out)
    return text

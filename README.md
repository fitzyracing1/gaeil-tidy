# gaeil-tidy

Turns rough, mixed-style notes into runnable [Gaeil](https://github.com/fitzyracing1/Gaeil) code (Irish-language Python).

Gaeil is the language; this helper is a **rule-based** tidier (no AI, no extra dependencies). It lowercases and translates keywords, converts C-style braces and comments, and comments out anything it still cannot compile so the result always runs. Every change is printed in a short report; nothing is guessed silently.

Site: [https://fitzyracing1.github.io/Gaeil/](https://fitzyracing1.github.io/Gaeil/)

## Install

```bash
pipx install git+https://github.com/fitzyracing1/gaeil-tidy
```

Or from a checkout:

```bash
pip install -e .
```

## Usage

Print cleaned Gaeil to stdout (the change report goes to stderr):

```bash
gaeil-tidy file.gaeil
python -m gaeil_tidy file.gaeil
```

Write a new file named `file.tidy.gaeil` (the original is never overwritten):

```bash
gaeil-tidy --write file.gaeil
```

Tidy and run the result:

```bash
gaeil-tidy --run file.gaeil
```

## Tidy rough notes

The tidier is built for messy drafts — mixed English and Irish keywords, braces, `//` comments, leftover semicolons, and `i++`. It will:

- Normalize keywords case-insensitively to Gaeil (`Feidhm` → `feidhm`, `If` → `má`, `Print` → `scríobh`, `def`/`return`/`True`/`False`/`None` → `feidhm`/`fill`/`fíor`/`bréag`/`neamhní`, and so on).
- Keep `import` as `import`, and rewrite `pytorch` to `torch` (with a note in the report).
- Convert `{ }` braces to colons and indentation, `//` comments to `#`, `i++`/`i--` to `i += 1`/`i -= 1`, and strip leftover `;`.
- Comment plain English sentences.
- Recover a function sketch when the notes have an unnamed `feidhm`, a quoted name, a parameter used in a condition, and shorthand like `1/2z`. Those recoveries are always listed in the report.
- Leave any line that still does not compile in place as `# GAEIL-TODO:` plus a short reason, so the output always runs.

Example, from a rough draft in `examples/notes/coax.gaeil`:

```gaeil
feidhm coax(n):
    # Gravitas
    # Working
    má n <= 0:
        fill 0
    fill n / 2
scríobh(coax(10))
```

That program prints `5.0`.

## Keywords

The keyword map is a standalone copy of the one in [fitzyracing1/Gaeil](https://github.com/fitzyracing1/Gaeil):

| English | Gaeil      |
|---------|------------|
| print   | `scríobh`  |
| if      | `má`       |
| else    | `eile`     |
| while   | `fad`      |
| for     | `do`       |
| def     | `feidhm`   |
| return  | `fill`     |
| True    | `fíor`     |
| False   | `bréag`    |
| and     | `agus`     |
| or      | `nó`       |
| not     | `ní`       |
| input   | `léigh`    |
| None    | `neamhní`  |

## License

MIT. Copyright (c) 2026 Joshua Almeida (fitzyracing1).

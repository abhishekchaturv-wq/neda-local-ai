"""Bounded-context self-editing tools — the fix for the "memory wall" that
made NEDA hang/timeout when editing its own real source files (2026-08-14).

Root cause (see reference doc / project_local_ai_neda.md for the full
diagnosis): NEDA's model (32B, ~26GB alone) runs on a 36GB machine with
almost no headroom. write_self_file's "always send the COMPLETE file" safety
rule — a deliberate, correct fix for an earlier destructive-rewrite incident
— meant every real self-edit forced the model to hold an entire file (some
of NEDA's own files run 15-25KB) in its working context for a full
read-then-write round trip. That one-time prefill cost pushed memory
allocation past what the machine has free, forcing macOS into disk swap,
which is 100-1000x slower than RAM and looks exactly like a hang (near-0%
CPU, no error, no progress) — reproduced 6+ times live, confirmed via direct
memory measurement (free pages cratering in lockstep with each hang).

The fix is architectural, not another timeout/quantization tweak (those help
but don't remove the wall — see the same writeup): stop making file size the
thing that determines context size. search_self_code and read_self_range let
the model find and read only the relevant few lines instead of a whole file.
apply_self_patch lets it change those lines via an exact old-text match
without ever needing the full file in its own context — the actual read,
match, and write happen entirely in this Python process, on disk, server-side.

write_self_file (self_tools.py) still exists and is still the right tool for
a genuinely new file's worth of content or a restructuring too broad for a
single patch — this module doesn't replace it, it makes it the exception
instead of the only option.
"""
import re
import subprocess
import time
from pathlib import Path

from self_tools import (SELF_DIR, _EXCLUDED_DIRS, _resolve_self_path,
                         _backup_and_write)

# Cap on how many lines read_self_range will return in one call — this tool
# exists specifically to avoid re-creating the "whole file in context"
# problem, so a caller can't just ask for lines 1-9999 and land right back
# where write_self_file already was.
_MAX_RANGE_LINES = 250

_SEARCHABLE_SUFFIXES = (".py", ".html", ".js", ".css", ".md", ".sh")


def _iter_source_files():
    for p in sorted(SELF_DIR.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(SELF_DIR)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        if p.suffix in _SEARCHABLE_SUFFIXES:
            yield p, rel


def search_self_code(query: str, max_results: int = 20) -> list[dict]:
    """Search NEDA's own source (all .py/.html/.js/.css/.md/.sh files under
    ~/local-ai/) for a literal substring, returning file + line number for
    each match. Use this FIRST when you know what you're changing but not
    exactly where — it's much cheaper than reading whole files, and its
    output feeds directly into read_self_range and apply_self_patch's
    filename/context arguments.

    Args:
        query: literal text to search for (case-insensitive substring match,
            not a regex). e.g. "clearChat" or "attachBtn.onclick".
        max_results: cap on matches returned (default 20) — if you hit this
            cap, narrow the query rather than raising the limit.

    Returns:
        A list of {file, line, text} dicts, one per matching line, in file
        order. Empty list if nothing matched — try a shorter/different
        substring rather than assuming the thing doesn't exist.
    """
    needle = query.lower()
    out = []
    for path, rel in _iter_source_files():
        try:
            lines = path.read_text().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, start=1):
            if needle in line.lower():
                out.append({"file": str(rel), "line": i, "text": line.strip()})
                if len(out) >= max_results:
                    return out
    return out


def read_self_range(filename: str, start_line: int, end_line: int) -> str:
    """Read a bounded range of lines from one of NEDA's own source files —
    prefer this over read_self_file whenever you already know roughly where
    the relevant code is (e.g. from search_self_code), since it costs far
    less context than the whole file. Capped at 250 lines per call; for a
    genuinely unfamiliar file, a few targeted read_self_range calls (guided
    by search_self_code) are cheaper overall than one full read_self_file.

    Args:
        filename: relative path under ~/local-ai/, e.g. "web/index.html".
        start_line: first line to include (1-indexed).
        end_line: last line to include (inclusive). Capped to
            start_line + 250 if the range is larger than that.

    Returns:
        The requested lines, each prefixed with its line number (so the
        numbers can be used directly in a follow-up call), or an error.
    """
    path, err = _resolve_self_path(filename)
    if err:
        return err
    if not path.is_file():
        return f"error: {filename!r} not found under {SELF_DIR}"
    lines = path.read_text().splitlines()
    total = len(lines)
    if start_line < 1:
        start_line = 1
    if end_line > start_line + _MAX_RANGE_LINES:
        end_line = start_line + _MAX_RANGE_LINES
    if end_line > total:
        end_line = total
    if start_line > total:
        return f"error: file only has {total} lines, start_line {start_line} is past the end."
    snippet = lines[start_line - 1:end_line]
    numbered = "\n".join(f"{n:>5}  {l}" for n, l in enumerate(snippet, start=start_line))
    footer = f"\n\n[{filename}: showing lines {start_line}-{end_line} of {total}]"
    return numbered + footer


def _syntax_check(path: Path, new_content: str) -> str:
    """Best-effort validation before a patch reaches disk. Real for .py
    (compile()), a loose bracket-balance sanity check for .html/.js/.css —
    good enough to catch an obviously truncated/malformed patch without being
    fragile about real HTML/CSS syntax. Returns "" if OK, else an error string."""
    if path.suffix == ".py":
        try:
            compile(new_content, str(path), "exec")
        except SyntaxError as e:
            return f"error: patch produces invalid Python syntax: {e}"
        return ""
    if path.suffix in (".html", ".js", ".css"):
        for open_c, close_c in (("{", "}"), ("(", ")"), ("[", "]")):
            if new_content.count(open_c) != new_content.count(close_c):
                return (f"error: patch leaves {open_c!r}/{close_c!r} unbalanced "
                        f"({new_content.count(open_c)} vs {new_content.count(close_c)}) "
                        f"— likely an incomplete or misplaced edit.")
        return ""
    return ""


def apply_self_patch(filename: str, old: str, new: str) -> str:
    """Change a specific piece of one of NEDA's own source files WITHOUT
    needing the whole file in your context — this is the PREFERRED way to
    edit yourself, over write_self_file, for any targeted change. Reads the
    real file directly from disk in this process, finds your exact `old`
    text, replaces it with `new`, and writes the result — you only ever need
    to hold the small `old`/`new` snippets in context, not the surrounding
    file. This is the direct fix for the memory/timeout problem large
    self-edits used to cause.

    `old` must match EXACTLY ONE location in the file (exact substring,
    whitespace and all — copy it verbatim from a prior read_self_range or
    search_self_code call, don't retype it from memory). Zero matches or
    more than one match is refused with an error explaining which — for
    "more than one," include more surrounding text in `old` to make it
    unique rather than guessing which occurrence was meant.

    Runs a syntax check before writing (real for .py via compile(); a loose
    bracket-balance check for .html/.js/.css) and refuses a patch that would
    shrink the file by more than half (same guard as write_self_file) —
    nothing reaches disk if either check fails. Every successful patch is
    still backed up first, same as write_self_file. Requires restart_self()
    afterward to take effect, same as any other self-edit.

    Args:
        filename: relative path under ~/local-ai/, e.g. "web/index.html".
        old: the exact existing text to replace — must appear exactly once.
        new: the replacement text.

    Returns:
        A confirmation with the byte-size delta, or an error describing
        exactly what to fix (0 matches / multiple matches / syntax error /
        shrink-guard) — never silently no-ops.
    """
    path, err = _resolve_self_path(filename)
    if err:
        return err
    if not path.is_file():
        return f"error: {filename!r} not found under {SELF_DIR}"
    old_content = path.read_text()
    count = old_content.count(old)
    if count == 0:
        return ("error: that exact text was not found in the file. Copy it "
                "verbatim from a read_self_range or search_self_code result "
                "— whitespace and line breaks must match exactly.")
    if count > 1:
        return (f"error: that text matches {count} locations in the file — "
                f"ambiguous. Include more surrounding lines in `old` so it "
                f"identifies exactly one spot.")
    new_content = old_content.replace(old, new, 1)
    syntax_err = _syntax_check(path, new_content)
    if syntax_err:
        return syntax_err
    result = _backup_and_write(path, old_content, new_content)
    if result.startswith("error:"):
        return result
    delta = len(new_content) - len(old_content)
    sign = "+" if delta >= 0 else ""
    return (f"patched {filename}: {sign}{delta} chars ({len(old_content)} -> "
            f"{len(new_content)}). Call restart_self() to load this change.")

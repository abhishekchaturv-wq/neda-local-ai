"""NEDA's self-inspection and self-modification tools — the second deliberate
exception to the otherwise read-only design (the first is smc_tools.py for the
SMC Structure Scanner). Added 2026-08-14 after a concrete failure: asked to
"inspect yourself and see how you can decrease your response time," NEDA had
no way to actually look at its own code or measure its own performance, so it
answered from an unrelated BMC Helix performance-tuning doc that happened to
contain the phrase "response time" — a clean fabrication, see
feedback_neda_no_hallucination.md and project_local_ai_neda.md for the fuller
writeup (indexed into NEDA's own RAG collection, so it can retrieve this story
about itself too).

Scoped to exactly ~/local-ai/ — NEDA's own directory — and nothing else, same
safety pattern as smc_tools.py: no credential files (.hpm_token.json here),
no path traversal. The one thing this module can do that smc_tools.py can't:
restart the process that's running THIS code (restart_self), because unlike
the SMC Scanner's subprocess-per-call model, NEDA's own server is one
long-running process — a self_write followed by no restart just keeps
running the old code.

write_self_file backs up every overwritten file to self_backups/ and refuses
a drastic shrink of an existing file (2026-08-14, second occurrence same day):
asked to "enable drag and drop in your chat bar," the model called
write_self_file on web/index.html WITHOUT re-reading it in that turn, wholesale
replacing the real 248-line chat UI (SSE streaming, model picker, error
handling) with a 69-line stub that didn't even call the backend — chat was
completely broken, not just missing drag-and-drop — and then confidently
reported success. Caught only because a human had manually backed up the file
first; the tool itself had zero defense. This was a prompt-only rule
("read_self_file before write_self_file") that a 32B local model did not
reliably follow under a multi-round tool chain — prompting alone isn't
enough, so the guard now lives in code.

Extended 2026-08-14 (same day) with real self-improvement, per explicit user
instruction: create_tool() lets NEDA write brand-new tool files (not just edit
existing ones) into custom_tools/, which custom_tools_loader.py auto-discovers
at startup — so NEDA can add capabilities it doesn't have yet, without a human
hand-editing agent.py/server.py's TOOLS list each time. See learn_tools.py
(persistent notes) and pip_tools.py (gated package installs) for the other two
pieces of this same instruction.
"""
import subprocess
import time
from pathlib import Path

SELF_DIR = Path.home() / "local-ai"
LATENCY_LOG = SELF_DIR / "logs" / "latency.jsonl"
CUSTOM_TOOLS_DIR = SELF_DIR / "custom_tools"

_CREDENTIAL_FILES = {".hpm_token.json"}
# Caught live 2026-08-14: asked to "improve response time," the model called
# create_tool() with a function whose body was literally a comment saying what
# it would do instead of doing it. A syntax-valid stub still passes compile(),
# so it needs its own check.
_PLACEHOLDER_MARKERS = (
    "placeholder for actual implementation",
    "todo: implement",
    "not yet implemented",
    "# todo implement",
)
# Anything under these subdirs is data/generated, not source — keep the tool
# focused on actual code files, not vector DB internals or crawl dumps.
_EXCLUDED_DIRS = {"chroma_db", "venv", "__pycache__", "logs"}


def list_self_files() -> list[str]:
    """List NEDA's own source files (Python + the web UI), so you know what
    exists before trying to read or modify anything.

    Returns:
        Filenames (relative to ~/local-ai/), source files only — excludes the
        vector DB, venv, caches, and logs.
    """
    out = []
    for p in sorted(SELF_DIR.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(SELF_DIR)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.name in _CREDENTIAL_FILES:
            continue
        if p.suffix in (".py", ".html", ".js", ".css", ".plist", ".md", ".sh"):
            out.append(str(rel))
    return out


def read_self_file(filename: str) -> str:
    """Read one of NEDA's own source files — use this for ANY question about
    how you work, what tools you have, your system prompt, your architecture,
    or your performance. Never answer such questions from retrieved context or
    general knowledge; read the actual file first.

    Args:
        filename: relative path under ~/local-ai/, as returned by
            list_self_files(), e.g. "server.py", "agent.py", "self_tools.py",
            "web/index.html".

    Returns:
        The file's full text, or an error message. Refuses credential files
        (.hpm_token.json) and anything outside ~/local-ai/.
    """
    try:
        path = (SELF_DIR / filename).resolve()
    except Exception:
        return f"error: invalid path {filename!r}"
    if SELF_DIR.resolve() not in path.parents and path != SELF_DIR:
        return "error: path escapes ~/local-ai/, refused."
    if path.name in _CREDENTIAL_FILES:
        return "error: credential files are not readable via this tool."
    if not path.is_file():
        return f"error: {filename!r} not found under {SELF_DIR}"
    return path.read_text()


BACKUPS_DIR = SELF_DIR / "self_backups"
# Below this, the shrink-guard doesn't apply — tiny files can legitimately
# shrink a lot (e.g. clearing a near-empty config) without it being a sign of
# a wholesale, context-blind rewrite.
_SHRINK_GUARD_MIN_CHARS = 500
_SHRINK_GUARD_RATIO = 0.5  # new content below this fraction of old = refused


def _resolve_self_path(filename: str):
    """Shared path resolution + safety checks for every self_tools function
    that touches a file. Returns (path, None) on success or (None, error_str)."""
    try:
        path = (SELF_DIR / filename).resolve()
    except Exception:
        return None, f"error: invalid path {filename!r}"
    if SELF_DIR.resolve() not in path.parents and path != SELF_DIR:
        return None, "error: path escapes ~/local-ai/, refused."
    if path.name in _CREDENTIAL_FILES:
        return None, "error: refusing to touch credential files via this tool."
    return path, None


def _backup_and_write(path, old_content: str, new_content: str) -> str:
    """Shared write path for write_self_file and apply_self_patch: enforces
    the shrink-guard, backs up the old content, writes the new content. Caller
    has already confirmed old_content is the file's real current content.
    Returns a confirmation string; caller returns this directly as the tool
    result on success. Raises nothing — shrink-guard rejection is the only
    failure path and is returned as a string starting with "error:"."""
    if (len(old_content) > _SHRINK_GUARD_MIN_CHARS
            and len(new_content) < len(old_content) * _SHRINK_GUARD_RATIO):
        return (f"error: refused. New content is {len(new_content)} chars vs "
                f"the current {len(old_content)} chars — over half the file "
                f"would be lost. This looks like a from-scratch rewrite, not "
                f"an edit.")
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUPS_DIR / f"{path.name}.{int(time.time())}.bak"
    backup_path.write_text(old_content)
    path.write_text(new_content)
    return (f"wrote {len(new_content)} chars to {path} (backed up previous "
            f"{len(old_content)} chars to {backup_path}). Call restart_self() "
            f"to load this change.")


def write_self_file(filename: str, content: str) -> str:
    """Overwrite one of NEDA's own source files with COMPLETE new content.
    EXCEPTIONAL PATH, not the normal one — prefer apply_self_patch for any
    targeted change (it doesn't require you to hold the whole file in context,
    which is what causes memory/timeout problems on large files). Use this
    only for a genuinely new file's worth of content, a full restructuring
    too broad for a single patch, or when apply_self_patch's exact-match
    requirement can't locate the target text. The change does NOT take effect
    until you also call restart_self() — you keep running the old code in
    this process until then. Tell the user a restart is happening when you do
    this.

    SAFETY: refuses credential files and anything outside ~/local-ai/. Only
    edits files that already exist. Every overwrite is backed up first to
    self_backups/<filename>.<timestamp>.bak, so a bad write is recoverable.
    On an existing file bigger than 500 chars, a new version under half the
    old size is REFUSED outright (error returned, nothing written) — this
    means you must read_self_file the current content and write back the
    FULL file with your change merged in, never a from-scratch replacement.
    A past incident wrote a 69-line stub over a real 248-line file and broke
    it silently; this check exists specifically to catch that pattern before
    it reaches disk. If a genuine large deletion is truly intended, say so
    explicitly in your reply and explain why — don't just retry with padding
    to dodge the size check.

    Args:
        filename: relative path under ~/local-ai/, must already exist, e.g.
            "server.py".
        content: the COMPLETE new file content (not a diff/patch fragment).

    Returns:
        A confirmation message, or an error.
    """
    path, err = _resolve_self_path(filename)
    if err:
        return err
    if not path.is_file():
        return (f"error: {filename!r} does not exist under {SELF_DIR} — this "
                f"tool only edits existing files, it doesn't create new ones.")
    old_content = path.read_text()
    result = _backup_and_write(path, old_content, content)
    if result.startswith("error:"):
        return (result + f" Call read_self_file({filename!r}) to get the real "
                f"current content, then write_self_file with that content plus "
                f"your change merged in — or better, use apply_self_patch for "
                f"a targeted change instead of a full rewrite.")
    return result


def restart_self() -> str:
    """Restart the NEDA web server so a code change made with write_self_file
    actually takes effect. This kills and relaunches the current process
    (launchd's KeepAlive brings it straight back up). When called from the web
    UI, the actual kill is deferred until your current response has finished
    sending, so it's safe to call this in the same turn as your explanation —
    you don't need a separate follow-up turn.

    Returns:
        Confirmation the restart was triggered, or an error.
    """
    import os
    try:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.neda.server"],
            capture_output=True, text=True, timeout=15,
        )
        return "restart triggered via launchctl kickstart — server will be back up in a few seconds."
    except Exception as e:
        return f"error triggering restart: {e}"


def self_status() -> str:
    """Report NEDA's own real, measured status — use this for ANY question
    about performance, response time, or "how am I doing," instead of
    guessing or generic advice. Includes recent actual response-time
    measurements (not estimates), the models in use, and process uptime.

    Returns:
        A short multi-line status report.
    """
    lines = []
    lines.append("hardware note: ~7 tokens/sec on this machine (Ollama, local CPU/GPU) — "
                  "see project_local_ai_neda memory for the source of this figure.")
    lines.append('models: coder=qwen2.5-coder:32b, reasoner=deepseek-r1:32b, vision=qwen2.5vl:7b')
    if LATENCY_LOG.exists():
        try:
            lines_raw = LATENCY_LOG.read_text().strip().splitlines()[-20:]
            import json
            entries = [json.loads(l) for l in lines_raw if l.strip()]
            if entries:
                avg = sum(e["elapsed_s"] for e in entries) / len(entries)
                worst = max(entries, key=lambda e: e["elapsed_s"])
                lines.append(f"last {len(entries)} responses: avg {avg:.1f}s, "
                              f"slowest {worst['elapsed_s']:.1f}s "
                              f"(model={worst['model']}, rounds={worst['rounds']}, "
                              f"tool_calls={worst['tool_calls']})")
                by_rounds = sum(1 for e in entries if e["rounds"] > 1)
                lines.append(f"{by_rounds}/{len(entries)} of those needed more than one "
                              f"model round (i.e. at least one tool call) — each extra "
                              f"round is a full extra model generation, the single "
                              f"biggest latency lever available.")
            else:
                lines.append("latency log exists but is empty — no measurements yet.")
        except Exception as e:
            lines.append(f"could not read latency log: {e}")
    else:
        lines.append("no latency measurements logged yet — ask a question first, "
                      "then check again.")
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        loaded = "com.neda.server" in r.stdout
        lines.append(f"com.neda.server launchd job: {'loaded' if loaded else 'NOT loaded'}")
    except Exception as e:
        lines.append(f"launchctl check failed: {e}")
    return "\n".join(lines)


def create_tool(filename: str, code: str) -> str:
    """Create a brand-new tool for yourself by writing a Python file under
    custom_tools/ — this is how you gain a capability you don't already have,
    rather than editing your core files. Every top-level function in the file
    that has a proper docstring (Args/Returns, same style as your existing
    tools) is auto-loaded as a usable tool the next time you start.

    Not live immediately: call restart_self() afterward to load it. Rejected
    before writing if the code has a syntax error (checked with compile())
    so a bad write can never break the next startup. Also rejected if it
    looks like a placeholder/stub (a comment describing what the code would
    do instead of real logic) — research the real approach with web_search
    and web_fetch first, then write working code based on what you found.

    Args:
        filename: bare "*.py" name, no path separators, no leading underscore
            (those are skipped by the loader), e.g. "candle_pattern_finder.py".
        code: the COMPLETE file content — imports, function(s), docstrings.

    Returns:
        Confirmation + reminder to restart, or a syntax/validation error.
    """
    name = Path(filename).name
    if not name.endswith(".py") or name != filename:
        return "error: filename must be a bare '*.py' name, no path separators."
    if name.startswith("_"):
        return "error: filenames starting with '_' are skipped by the loader, won't be picked up."
    try:
        compile(code, name, "exec")
    except SyntaxError as e:
        return f"error: syntax error in the code, not saved: {e}"
    lowered = code.lower()
    if any(m in lowered for m in _PLACEHOLDER_MARKERS):
        return ("error: this reads as a placeholder/stub, not a real implementation "
                "(matched phrasing like 'placeholder for actual implementation' or "
                "'not yet implemented'). Research the real approach first — "
                "web_search / web_fetch for how to actually do this in Python — "
                "then write working code based on what you found. Not saved.")
    CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    (CUSTOM_TOOLS_DIR / name).write_text(code)
    return (f"wrote {CUSTOM_TOOLS_DIR / name} ({len(code)} chars). Call "
            f"restart_self() to load it — every top-level function with a "
            f"docstring becomes a usable tool automatically.")


def list_custom_tools() -> str:
    """List your self-created tools (custom_tools/) and which ones actually
    loaded successfully into your current toolset vs. failed and why.

    Returns:
        One line per file: loaded (with tool count) or failed (with the error).
    """
    from custom_tools_loader import load_custom_tools
    _, report = load_custom_tools()
    return "\n".join(report) if report else "no custom tools yet — use create_tool() to add one."

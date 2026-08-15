"""NEDA's own accumulating notes — separate from Claude's memory system
(~/.claude/projects/-Users-abchatur/memory/), this is knowledge NEDA writes for
itself: when the user tells it to remember something, or when it learns a fact
worth keeping across conversations. Indexed into the same RAG collection as
the regular memory files and Pine scripts (see index_knowledge.py, extended
2026-08-14 to also glob this directory) via reindex_knowledge().
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path

LEARNED_DIR = Path.home() / "local-ai" / "learned"


def remember(note: str, tag: str = "general") -> str:
    """Save a note to your own persistent knowledge so you can recall it in
    future conversations, after a reindex_knowledge() call. Use this when the
    user tells you to remember something, or you learn a fact/correction
    worth keeping — not for ephemeral conversation content.

    Args:
        note: the fact/correction to remember, written so it makes sense read
            cold later — no "as I just said," a future you won't have this
            conversation's context.
        tag: short category, becomes the filename, e.g. "smc-scanner",
            "trading-preferences", "general". Notes sharing a tag append to
            the same file.

    Returns:
        Confirmation, including a reminder that reindex_knowledge() is needed
        before this note is actually searchable via retrieval.
    """
    safe_tag = re.sub(r"[^a-z0-9_-]", "-", tag.lower()) or "general"
    LEARNED_DIR.mkdir(parents=True, exist_ok=True)
    path = LEARNED_DIR / f"{safe_tag}.md"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with path.open("a") as f:
        f.write(f"\n## {stamp}\n{note}\n")
    return f"saved to {path}. Call reindex_knowledge() to make it searchable."


def recall_notes(tag: str = "") -> str:
    """List or read your own saved notes directly — for a quick exact check,
    as opposed to the semantic retrieval that already runs on every question
    once reindex_knowledge() has been run at least once since the note was saved.

    Args:
        tag: if given, read that tag's file in full. If empty, list every tag
            that exists.

    Returns:
        The requested content, or the list of available tags.
    """
    if not LEARNED_DIR.exists():
        return "no notes saved yet."
    if not tag:
        tags = sorted(p.stem for p in LEARNED_DIR.glob("*.md"))
        return "tags: " + ", ".join(tags) if tags else "no notes saved yet."
    safe_tag = re.sub(r"[^a-z0-9_-]", "-", tag.lower())
    path = LEARNED_DIR / f"{safe_tag}.md"
    if not path.exists():
        return f"no notes under tag {tag!r}."
    return path.read_text()


def reindex_knowledge() -> str:
    """Re-run the knowledge indexer so newly remembered notes become
    searchable in your retrieval context. Takes a few seconds to a minute.
    Call this after remember() (and after create_tool(), to make a new
    tool's own source findable too — though list_custom_tools() is the more
    direct way to check that).

    Returns:
        The indexer's summary output, or an error.
    """
    script = Path.home() / "local-ai" / "index_knowledge.py"
    py = Path.home() / "local-ai" / "venv" / "bin" / "python"
    try:
        r = subprocess.run([str(py), str(script)], capture_output=True, text=True, timeout=120)
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return out[-2000:] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "error: indexing timed out after 120s"
    except Exception as e:
        return f"error: {e}"

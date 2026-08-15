"""Shared per-Ollama-call telemetry for server.py and agent.py — the
measurement the 2026-08-14 memory-wall investigation kept redoing manually
(ps/vm_stat/memory_pressure by hand, once per hypothesis, across many live
tests). Logs prompt size, context config, and free-memory delta for every
single round to logs/ollama_telemetry.jsonl, so a future "why did this hang"
question has real per-call numbers instead of needing a fresh live repro.

Built alongside self_patch.py (the actual fix — bounded-context edits instead
of whole-file round trips) so the new patch tool's effect on prompt size is
directly measurable rather than assumed.
"""
import json
import subprocess
import time
from pathlib import Path

OLLAMA_TELEMETRY_LOG = Path.home() / "local-ai" / "logs" / "ollama_telemetry.jsonl"


def vm_free_bytes():
    """System-wide free memory via vm_stat, ~5ms. Not per-process, but this
    is exactly the signal used to manually diagnose the memory-wall hangs
    (free pages cratering in lockstep with each hang). Returns None if
    vm_stat isn't available (non-macOS) rather than raising — telemetry is a
    diagnostic nice-to-have, never worth failing a real request over."""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            if line.startswith("Pages free:"):
                pages = int(line.split(":")[1].strip().rstrip("."))
                return pages * 16384  # this Mac's page size; see vm_stat's own header line
    except Exception:
        pass
    return None


def log_ollama_call(*, round_i, messages, tools_count, num_ctx, model,
                     free_before, free_after, elapsed_s, success, error=None,
                     source="server"):
    """Log one Ollama /api/chat call's telemetry. `source` distinguishes the
    web server (server.py) from the CLI (agent.py) in the shared log file.
    Rough token estimate only (chars/4) — good enough to compare requests
    relatively, not meant as an exact tokenizer count."""
    OLLAMA_TELEMETRY_LOG.parent.mkdir(parents=True, exist_ok=True)
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    entry = {
        "ts": time.time(), "source": source, "model": model, "round": round_i,
        "message_count": len(messages), "prompt_chars": prompt_chars,
        "prompt_tokens_est": prompt_chars // 4, "tools_count": tools_count,
        "num_ctx": num_ctx, "free_before_bytes": free_before,
        "free_after_bytes": free_after,
        "free_delta_bytes": (None if free_before is None or free_after is None
                              else free_after - free_before),
        "elapsed_s": round(elapsed_s, 2), "success": success, "error": error,
    }
    with OLLAMA_TELEMETRY_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")

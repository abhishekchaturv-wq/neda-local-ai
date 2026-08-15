"""Lets NEDA install new Python packages into its own venv — for tools it
creates (see self_tools.create_tool) that need a library it doesn't already
have. Real risk, stated plainly: pip install runs arbitrary setup/build code
from PyPI, same as a human running pip install by hand. Granted here because
the user explicitly asked for NEDA to be able to download/install what it
needs (2026-08-14). Guardrails: exactly one simple package spec per call (no
flags, no multiple packages, no arbitrary index URLs or VCS specs), and a
fixed blocklist of this codebase's own core dependencies, so a bad install
can't take down the very server NEDA runs in with no easy way to self-recover.
"""
import re
import subprocess
from pathlib import Path

VENV_PIP = Path.home() / "local-ai" / "venv" / "bin" / "pip"

# What agent.py/server.py/the existing tool modules actually import. A
# conflicting version of any of these risks breaking the process NEDA runs
# in — possibly to the point the server can't even start to fix itself.
# Unrelated new packages for new tools are unaffected by this list.
_CORE_PACKAGES = {"ollama", "chromadb", "flask", "kiteconnect", "pandas",
                   "numpy", "beautifulsoup4", "bs4"}

_SPEC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(==[A-Za-z0-9.]+)?$")


def pip_install(package: str) -> str:
    """Install a Python package into your own venv — use this when a new tool
    you're creating (via create_tool) needs a library you don't already have.

    Args:
        package: a single simple package spec, e.g. "requests" or
            "requests==2.31.0". No flags, no multiple packages, no URLs or VCS
            specs — those are rejected outright.

    Returns:
        pip's output, or an error. Refuses to touch this codebase's own core
        dependencies (ollama, chromadb, flask, kiteconnect, pandas, numpy,
        beautifulsoup4) — a version conflict there could break the server
        this code runs in, with no easy self-recovery path.
    """
    spec = package.strip()
    if not _SPEC_RE.match(spec):
        return ("error: invalid package spec — only a bare name or "
                "name==version is allowed, no flags/URLs/multiple packages.")
    base_name = spec.split("==")[0].lower()
    if base_name in _CORE_PACKAGES:
        return (f"error: refusing to touch {base_name!r} — it's a core "
                f"dependency of the agent you're running in. A version "
                f"conflict there could break the server with no easy "
                f"self-recovery. If this is genuinely needed, tell the user "
                f"directly rather than installing it yourself.")
    try:
        r = subprocess.run([str(VENV_PIP), "install", spec],
                           capture_output=True, text=True, timeout=180)
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return out[-3000:] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "error: pip install timed out after 180s"
    except Exception as e:
        return f"error: {e}"

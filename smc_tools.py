"""Run, inspect, and modify the SMC Structure Scanner — the ONE place in this
codebase where NEDA has write/execute access, by explicit user instruction
(2026-08-14): "teach NEDA everything about SMC Structure Scanner so that it can
run it independently and modify it further without any dependency on you."

Every other tool module here (hpm_readonly.py, pine_readonly.py) stays strictly
read-only by design — this module is the deliberate, narrow exception, scoped to
exactly one directory (~/kite-test/apex-lab/local/) and nothing else. It must
never be imported for any purpose beyond the SMC Scanner.

Background this module assumes NEDA already knows (also written into
~/.claude/projects/-Users-abchatur/memory/project_smc_structure_scanner.md,
which index_knowledge.py embeds into NEDA's own RAG collection — ask NEDA
about "SMC scanner" or "SMC structure" to retrieve the full writeup):

- Two-stage design: `build-levels` (slow, ~2min, needs a Kite token, computes
  swing-structure highs/lows from 200 days of 30-min history) writes
  smc_levels.parquet; `scan` (fast) compares live LTP against those cached
  levels. Recomputing structure on every scan would blow the Kite rate limit,
  so they're deliberately decoupled.
- THE BUG THIS MODULE EXISTS BECAUSE OF (2026-08-14): smc_levels.parquet goes
  stale after 3 days (_staleness_guard, max_age_days=3) and NOTHING was
  re-running build-levels automatically — the scheduled `com.apex.smcscan`
  launchd job only ever calls `scan`. Once every symbol's history crossed the
  3-day mark, every scheduled scan silently printed "no symbols with fresh
  enough history" and returned before ever even checking the Kite token —
  which is why it looked like an auth problem but wasn't (the token was fine,
  verified via `kite_auth.py check`). Fixed by running build-levels once
  manually and adding a new daily `com.apex.smcbuild` launchd job (9:00 AM
  weekdays, before the first 9:30 scan) so this can't silently recur. If scans
  ever go quiet again, check levels-cache age FIRST via smc_status() below,
  before assuming it's a credentials problem.
- Kite access tokens expire ~06:00 IST daily and need an interactive login —
  that's what the /token page (served by `serve`, already running permanently
  under launchd as com.apex.smcserve on port 8765) is for. NEDA cannot do this
  step itself (it's a real 2FA browser login), only check whether it's been
  done (smc_status()).
"""
import subprocess
from pathlib import Path

SMC_DIR = Path.home() / "kite-test" / "apex-lab" / "local"
SMC_SCRIPT = SMC_DIR / "smc_scanner.py"
VENV_PY = Path.home() / "kite-test" / "apex-lab" / ".venv" / "bin" / "python"

# "serve" excluded: it's a permanent process already running under launchd
# (com.apex.smcserve on port 8765) — starting a second one just port-conflicts.
# "watch" excluded from unattended use: it loops forever until Ctrl-C, which
# would hang a tool call. Use "scan" for a single pass instead.
ALLOWED_SUBCOMMANDS = {"build-levels", "scan", "drill", "queue", "mark-drawn"}

_CREDENTIAL_FILES = {".kite_config", ".kite_token"}


def run_smc_scanner(subcommand: str, args: str = "") -> str:
    """Run one smc_scanner.py subcommand and return its output.

    Args:
        subcommand: One of "build-levels", "scan", "drill", "queue", "mark-drawn".
            "watch" and "serve" are deliberately not allowed here — "watch" loops
            forever (would hang), "serve" is already running permanently under
            launchd on port 8765, starting a second one just errors on the port.
            For a single scan pass, use "scan", not "watch".
        args: Extra CLI flags as one string, e.g. "--pct 0.3" or
            "--universe fno --days 100". Optional, default none.

    Returns:
        The command's combined stdout/stderr (trimmed to the last ~6000 chars),
        or an error message if the subcommand isn't allowed or it times out.
    """
    if subcommand not in ALLOWED_SUBCOMMANDS:
        return (f"error: {subcommand!r} not allowed here. Choose from "
                f"{sorted(ALLOWED_SUBCOMMANDS)}. (watch loops forever and serve is "
                f"already running permanently under launchd on port 8765.)")
    cmd = [str(VENV_PY), str(SMC_SCRIPT), subcommand] + (args.split() if args else [])
    try:
        r = subprocess.run(cmd, cwd=SMC_DIR, capture_output=True, text=True, timeout=180)
        out = r.stdout + (("\nSTDERR:\n" + r.stderr) if r.stderr else "")
        return out[-6000:] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "error: timed out after 180s"
    except Exception as e:
        return f"error running smc_scanner: {e}"


def read_smc_file(filename: str) -> str:
    """Read a file from the SMC Scanner's own directory (source code, dashboard
    template, launchd-adjacent scripts — NOT credentials, see below).

    Args:
        filename: filename only (no path), e.g. "smc_scanner.py", "kite_auth.py",
            "dashboard.py". Must exist directly inside the scanner's directory —
            no path traversal, no subdirectories.

    Returns:
        The file's full text, or an error message. Refuses .kite_config and
        .kite_token outright (even redacted) — use smc_status() to check auth
        state instead of reading the credential files directly.
    """
    name = Path(filename).name
    if name in _CREDENTIAL_FILES:
        return ("error: credential files are not readable via this tool, even "
                "redacted. Use smc_status() to check auth state instead.")
    path = SMC_DIR / name
    if not path.is_file():
        return f"error: {filename!r} not found in {SMC_DIR}"
    return path.read_text()


def write_smc_file(filename: str, content: str) -> str:
    """Overwrite a file in the SMC Scanner's directory with new content — this is
    how NEDA modifies the scanner's own code (e.g. smc_scanner.py, dashboard.py).

    SAFETY: refuses credential files and anything outside this one directory.
    Only edits files that already exist (won't silently create new ones in the
    wrong place). Does NOT keep a backup — there's no version control in this
    directory, so an overwrite is not trivially undoable. Prefer showing the
    intended change and reasoning in your own reply first when you're not fully
    confident in it, rather than writing directly.

    Args:
        filename: filename only (no path), must already exist in the scanner's
            directory, e.g. "smc_scanner.py".
        content: the COMPLETE new file content (not a diff or patch fragment).

    Returns:
        A confirmation message, or an error.
    """
    name = Path(filename).name
    if name in _CREDENTIAL_FILES:
        return "error: refusing to write credential files via this tool."
    path = SMC_DIR / name
    if not path.exists():
        return (f"error: {filename!r} does not exist in {SMC_DIR} — this tool "
                f"only edits existing files, it doesn't create new ones.")
    path.write_text(content)
    return f"wrote {len(content)} chars to {path}"


def smc_status() -> str:
    """Check SMC Scanner health in one call: how old the cached structure-levels
    are (they go stale and get silently excluded after 3 days — see this file's
    module docstring for the 2026-08-14 incident this caused), whether the Kite
    token is currently valid, and whether the three launchd jobs are loaded.

    Returns:
        A short multi-line status report.
    """
    from datetime import datetime
    levels = Path.home() / "kite-test" / "apex-data-lake" / "derived" / "smc_levels.parquet"
    lines = []
    if levels.exists():
        age_h = (datetime.now().timestamp() - levels.stat().st_mtime) / 3600
        flag = "  <-- getting close to the 72h staleness cutoff" if age_h > 60 else ""
        lines.append(f"levels cache: {age_h:.1f}h old (stale/excluded past 72h){flag}")
    else:
        lines.append("levels cache: MISSING — run build-levels before anything else")
    try:
        r = subprocess.run([str(VENV_PY), str(SMC_DIR / "kite_auth.py"), "check"],
                           cwd=SMC_DIR, capture_output=True, text=True, timeout=20)
        lines.append(f"kite auth: {(r.stdout or r.stderr).strip()}")
    except Exception as e:
        lines.append(f"kite auth check failed to run: {e}")
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        for label in ("com.apex.smcserve", "com.apex.smcscan", "com.apex.smcbuild"):
            lines.append(f"{label}: {'loaded' if label in r.stdout else 'NOT loaded'}")
    except Exception as e:
        lines.append(f"launchctl check failed: {e}")
    return "\n".join(lines)

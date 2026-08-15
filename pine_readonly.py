"""Read-only access to the user's Pine Script library. No writes — per the standing
versioning rule, .pine files are never overwritten, only ever appended as new -vN
files by hand, so this stays out of the local agent's tool access entirely."""
from pathlib import Path

PINE_DIR = Path.home() / "pine-scripts"


def list_pine_scripts() -> list[str]:
    """List every Pine Script file the user has, by filename.

    Returns:
        A list of .pine filenames (no path, no content).
    """
    return sorted(p.name for p in PINE_DIR.glob("*.pine"))


def read_pine_script(filename: str) -> str:
    """Read the full contents of one Pine Script file.

    Args:
        filename: Exact filename, e.g. "apex-suite-v8.pine". Must be a .pine file
            already listed by list_pine_scripts() — no path traversal allowed.

    Returns:
        The file's raw text content, or an error message if not found.
    """
    name = Path(filename).name  # strip any path component, defense in depth
    if not name.endswith(".pine"):
        return f"error: {filename!r} is not a .pine file"
    path = PINE_DIR / name
    if not path.exists():
        return f"error: {name!r} not found in {PINE_DIR}"
    return path.read_text()

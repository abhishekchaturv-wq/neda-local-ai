"""Dynamically loads NEDA's self-authored tools from ~/local-ai/custom_tools/*.py
so a new tool created via self_tools.create_tool() becomes usable after a
restart, without needing agent.py/server.py's own TOOLS list hand-edited every
time. Deliberately fails soft: a broken custom tool file is skipped with a
one-line report, never crashes startup for the whole agent.
"""
import importlib.util
import sys
from pathlib import Path

CUSTOM_TOOLS_DIR = Path.home() / "local-ai" / "custom_tools"


def load_custom_tools():
    """Import every .py file in custom_tools/ and collect its public,
    docstring-bearing functions as tools.

    Returns:
        (tools, report) — tools is a list of callables ready to append to a
        TOOLS list; report is a list of one-line strings describing what
        loaded (and how many functions) or failed (and why), used both for a
        startup printout and by self_tools.list_custom_tools().
    """
    tools = []
    report = []
    if not CUSTOM_TOOLS_DIR.exists():
        return tools, report
    for path in sorted(CUSTOM_TOOLS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        mod_name = f"neda_custom_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
        except Exception as e:
            report.append(f"FAILED to load {path.name}: {e}")
            continue
        found = 0
        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            attr = getattr(mod, attr_name)
            if (callable(attr) and getattr(attr, "__module__", None) == mod_name
                    and attr.__doc__):
                tools.append(attr)
                found += 1
        report.append(f"loaded {path.name}: {found} tool(s)")
    return tools, report

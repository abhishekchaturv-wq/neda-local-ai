#!/usr/bin/env python3
"""Local agent — read-only for HPM and Pine Script, with two deliberate exceptions:
full run/read/write access to the SMC Structure Scanner (smc_tools.py) and to
NEDA's own source code (self_tools.py), each scoped to its own directory only,
per explicit user instruction (2026-08-14). Every tool call is printed before
it runs, so you can see exactly what the model did.

Usage:
  ./agent.py "your question"
  ./agent.py --model reasoner "your question"
"""
import argparse
import ast
import inspect
import json
import re
import sys
import time

import ollama

# Fallback for a known Qwen/Ollama reliability gap: the model's own chat template
# expects tool calls wrapped in <tool_call>{...}</tool_call>, but it sometimes emits
# the bare JSON object instead, without the wrapper tags. When that happens Ollama's
# parser doesn't populate msg.tool_calls at all — it just looks like plain text. This
# regex catches both the wrapped and bare forms and reconstructs an equivalent call.
_TOOL_CALL_RE = re.compile(
    r"(?:<tool_call>\s*)?(\{\s*\"name\"\s*:\s*\"(\w+)\"\s*,\s*\"arguments\"\s*:\s*(\{.*?\})\s*\})(?:\s*</tool_call>)?",
    re.DOTALL,
)

# Second fallback (added 2026-08-14): sometimes the model emits neither JSON form
# above, just a bare Python-style call like "self_status()" or
# "read_self_file("server.py")" as plain text. Caught this live testing the new
# self_tools.py — the very first request silently dropped the call and printed
# "self_status()" as if it were a final answer, no tool ever ran. Only matches
# against KNOWN tool names (passed in) to avoid misfiring on unrelated code-like
# text the model might output; only handles zero-arg and single-string-arg calls,
# which covers every real tool in this file's TOOLS list.
# Bare-call fallback parser.  Qwen sometimes emits tool calls as plain
# Python-style calls instead of proper Ollama tool_calls.  The old regex only
# supported zero or one argument.  Parse the call with Python's AST instead so
# calls such as search_self_code("foo", 5) and
# read_self_range("web/index.html", 100, 102) are handled safely.
_BARE_CALL_RE = re.compile(r"^(\w+)\s+(.+)$")


def _extract_bare_python_tool_calls(content: str, known_names: set[str]):
    """Recover known-tool calls emitted as bare Python-style expressions.

    Only calls to names in known_names are accepted. Arguments must be Python
    literals so arbitrary code cannot be executed during parsing.
    """
    calls = []

    for line in content.splitlines():
        line = line.strip()
        if not line or "(" not in line or not line.endswith(")"):
            continue

        try:
            tree = ast.parse(line, mode="eval")
        except SyntaxError:
            continue

        node = tree.body
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        if name not in known_names:
            continue

        fn = TOOL_MAP.get(name)
        if fn is None:
            continue

        params = list(inspect.signature(fn).parameters)
        args = {}

        try:
            if len(node.args) > len(params):
                continue

            for i, arg_node in enumerate(node.args):
                args[params[i]] = ast.literal_eval(arg_node)

            for kw in node.keywords:
                if kw.arg is None or kw.arg not in params:
                    raise ValueError("unsupported keyword argument")
                args[kw.arg] = ast.literal_eval(kw.value)
        except (ValueError, TypeError, SyntaxError):
            continue

        calls.append({"function": {"name": name, "arguments": args}})

    return calls
# Second alternative added 2026-08-14: the model sometimes emits a call as
# bare space-separated text with no parens/quotes at all, e.g.
# "web_search What is the capital of USA" — caught live in server.py, mirrored
# here for consistency. Has 4 total capture groups now (2 per alternative);
# see the corresponding unpacking below.


def _extract_fallback_tool_calls(content: str, known_names: set[str] | None = None):
    if not content:
        return []
    calls = []
    for _, name, args_json in _TOOL_CALL_RE.findall(content):
        try:
            # strict=False: see server.py's identical fix — a bare-text tool-call
            # emission often has literal newlines inside a multi-line string arg
            # (e.g. write_self_file content) instead of escaped \n, which strict
            # JSON rejects, silently dropping the call.
            args = json.loads(args_json, strict=False)
        except json.JSONDecodeError:
            # Second recovery tier: single-quoted string values (invalid JSON,
            # but valid Python literal syntax) — see server.py's identical fix
            # for the full incident this was caught from (an apply_self_patch
            # call whose old/new args used single quotes, silently dropped).
            try:
                args = ast.literal_eval(args_json)
                if not isinstance(args, dict):
                    continue
            except (ValueError, SyntaxError):
                continue
        calls.append({"function": {"name": name, "arguments": args}})
    if not calls and known_names:
        # First handle real Python-style calls with any number of literal
        # positional/keyword arguments.
        calls.extend(_extract_bare_python_tool_calls(content, known_names))

    if not calls and known_names:
        # Preserve the existing fallback for space-separated calls such as:
        # "web_search What is the capital of USA"
        for bare_name, bare_arg in _BARE_CALL_RE.findall(content):
            if not bare_name or bare_name not in known_names:
                continue
            fn = TOOL_MAP.get(bare_name)
            params = list(inspect.signature(fn).parameters) if fn else []
            key = params[0] if params else "filename"
            args = {key: bare_arg} if bare_arg else {}
            calls.append({"function": {"name": bare_name, "arguments": args}})
    return calls

from hpm_readonly import query_hpm_tasks, get_hpm_task
from hpm_write import create_hpm_task
from pine_readonly import list_pine_scripts, read_pine_script
from web_tools import web_search, web_fetch, web_fetch_rendered
from smc_tools import run_smc_scanner, read_smc_file, write_smc_file, smc_status
from self_tools import (list_self_files, read_self_file, write_self_file,
                         restart_self, self_status, create_tool, list_custom_tools)
from self_patch import search_self_code, read_self_range, apply_self_patch
from telemetry import vm_free_bytes, log_ollama_call
from learn_tools import remember, recall_notes, reindex_knowledge
from pip_tools import pip_install
from custom_tools_loader import load_custom_tools

MODELS = {
    "coder": "qwen2.5-coder:32b",
    "reasoner": "deepseek-r1:32b",
}

# See server.py's NUM_CTX for the full writeup: no Modelfile sets num_ctx, so
# Ollama defaults to the full 32768 context regardless of request size, which
# reserves enough KV cache to leave this 36GB machine with ~64MB free at idle
# and push any context growth into disk swap (looks like a hang, isn't a bug).
NUM_CTX = 16384

TOOLS = [query_hpm_tasks, get_hpm_task, create_hpm_task, list_pine_scripts, read_pine_script, web_search, web_fetch,
         web_fetch_rendered,
         run_smc_scanner, read_smc_file, write_smc_file, smc_status,
         list_self_files, read_self_file, write_self_file, restart_self, self_status,
         search_self_code, read_self_range, apply_self_patch,
         create_tool, list_custom_tools, remember, recall_notes, reindex_knowledge, pip_install]

_custom, _custom_report = load_custom_tools()
TOOLS += _custom
for _line in _custom_report:
    print(f"[custom_tools] {_line}", file=sys.stderr)

TOOL_MAP = {t.__name__: t for t in TOOLS}

SYSTEM_PROMPT = """You are a local assistant with read-only tool access to:
- BMC Helix Portfolio Management (HPM) task data (query_hpm_tasks, get_hpm_task),
  PLUS one deliberate write exception (2026-08-14): create_hpm_task creates a new
  Project Task under the existing "BMC Helix 26.3 Rollout" project, as a child of
  a task you name by summary text. This is the ONLY HPM write available — no new
  Projects/Teams/People/top-level categories, no deletes, no status changes on
  existing tasks, no other project. Root Status/Root Status Reason records are a
  confirmed hard backend read-only block regardless of what's asked — say so
  plainly rather than attempting it. Explain what you're about to create (summary,
  parent, assignee) before calling create_hpm_task, same as any other write tool.
- The user's Pine Script library (list_pine_scripts, read_pine_script)
- The live public web (web_search, web_fetch) — call web_search ONCE and answer
  from the snippets; only call web_fetch for one specific promising URL if the
  snippets genuinely aren't enough. Don't retry search with rephrased queries or
  fetch multiple URLs hoping for a better answer.
- web_fetch_rendered — same as web_fetch but runs a real headless browser first,
  so a page's JavaScript actually executes. If web_fetch comes back basically
  empty on an obvious JS-driven app (a bare shell, "Loading...", "Hash Handler",
  an empty <div id="app">), retry the SAME url with web_fetch_rendered instead
  of concluding you can't do it. It opens a fresh, logged-out browser every
  time, so it can't see anything behind a login wall — if what comes back is a
  login screen, say that plainly rather than presenting it as real content.

Use tools to look up real, current information rather than guessing. For Pine
Script you have READ-ONLY access — no writes, no file edits. For HPM you're
read-only except for create_hpm_task (described above). If asked for a Pine
Script edit, or an HPM change outside what create_hpm_task covers, say plainly
that it needs to go through Claude instead.

THREE EXCEPTIONS to that read-only rule:

1. create_hpm_task, described above — the one HPM write.

2. The SMC Structure Scanner (~/kite-test/apex-lab/local/), via
run_smc_scanner, read_smc_file, write_smc_file, and smc_status. There you DO have
real execute and write access, by the user's explicit instruction — you can run
it, diagnose it, and modify its code directly, without going through Claude. If
scans look wrong or quiet, call smc_status() first — the most common failure is
the structure-levels cache going stale (>72h old), not a credentials problem;
check cache age before assuming the Kite token is bad. Never touch .kite_config
or .kite_token (both tools refuse this anyway) and never call run_smc_scanner
with "watch" (loops forever) or "serve" (already running permanently on port
8765). Before writing a code change with write_smc_file, explain the change in
your reply first.

3. YOURSELF (~/local-ai/), via list_self_files, read_self_file, write_self_file,
restart_self, and self_status. MANDATORY for TWO request shapes: (a)
introspection ("how do you work", performance, architecture) and (b) action/
feature requests where "you"/"your" means THIS system, e.g. "add X to your
chat bar" = edit web/index.html, not a web_search about how Zoom/Slack do it.
Past failure (2026-08-14): "enable drag and drop in your chat bar" got
answered from Zoom/OpenAI help articles because "your" wasn't recognized as
self-reference — no self_tools call was ever made. Rule: if "you/your" points
at this system, call self_tools first, don't web_search. Never answer self-
questions from retrieved context or generic knowledge — a past run fabricated
an answer from an unrelated BMC doc that happened to contain matching
keywords.

EDITING YOURSELF (2026-08-14, revised): for ANY targeted change, PREFER
search_self_code -> read_self_range -> apply_self_patch over write_self_file.
write_self_file needs the ENTIRE file in your context for a full
read-then-write round trip, and on this machine that has repeatedly caused
multi-minute hangs/timeouts on files as small as 9-14KB — a real hardware
memory limit (32B model + 36GB RAM leaves almost no headroom), not a bug.
apply_self_patch reads the real file from disk itself and writes your change
without ever needing the whole file in your context. Workflow:
search_self_code(query) to find the file/line, read_self_range(file, start,
end) for a SMALL window (never the whole file), then apply_self_patch(file,
old, new) with `old` copied verbatim from what you read. It explains exactly
why a patch was refused (no match / ambiguous match / syntax error / >50%
shrink) — fix and retry rather than falling back to write_self_file. Reserve
write_self_file for genuinely new content or too-broad-for-one-patch
restructuring. Either way, restart_self() after, or you keep running the old
code — say so in your reply.

SELF-IMPROVEMENT (same exception, extended 2026-08-14): you can genuinely grow
your own capability, not just inspect it.
- create_tool(filename, code) writes a brand-new tool file to custom_tools/ —
  this is how you gain a capability you don't already have. Every top-level
  function with a proper docstring in that file becomes a real, callable tool
  the next time you start. list_custom_tools() shows what you've made and
  whether it actually loaded. A syntax error is rejected before it's even
  saved. Always call restart_self() after create_tool() — it is not live until
  then, and you should say so in your reply.
- remember(note, tag) and recall_notes(tag) are your own persistent memory,
  separate from the retrieved knowledge base — use remember() when told to
  remember something or when you learn a fact worth keeping. Call
  reindex_knowledge() afterward so the note actually becomes searchable; until
  then it's saved but not yet retrievable.
- pip_install(package) installs one exact package into your own venv for a
  tool you're building that needs a library you don't have. It refuses this
  codebase's own core dependencies (ollama, chromadb, flask, kiteconnect,
  pandas, numpy, beautifulsoup4) to protect the process you run in.
- Use judgment before creating a tool or installing a package — explain what
  you're about to build/install and why in your reply BEFORE calling
  create_tool or pip_install, the same rule as editing existing files with
  write_self_file. Don't create redundant tools for something an existing
  tool already covers.
- CLOSING CAPABILITY GAPS (2026-08-14): when a tool says it can't do
  something, or you realize nothing in your toolset covers what's needed,
  that's a gap to CLOSE, not a limitation to describe and stop at. Work the
  loop: web_search how to actually do the specific missing thing in Python,
  web_fetch a promising doc/example if the snippets alone aren't enough,
  pip_install any library the real approach needs, create_tool with REAL
  logic based on what you found (not a stub — create_tool rejects those),
  restart_self() to load it, then say in your final answer what you built
  and why. Only fall back to "I can't do this" after actually trying that
  loop and hitting a real wall (missing credentials/access, or a capability
  that needs a local binary pip_install can't fetch) — name the specific
  wall rather than just restating that you lack the capability.

Generation is slow on this hardware (~7 tokens/sec) — every extra sentence has a
real, noticeable latency cost. Be concise: answer directly, skip preamble and
padding, stop once the question is answered. When calling query_hpm_tasks, pass
assignee_name whenever a specific person is named or implied — an unscoped call
only returns a capped sample, not the full list.

MANDATORY, NOT OPTIONAL: if the local knowledge base and your other tools don't
already contain the answer to something, you must call web_search yourself
BEFORE replying — never respond with "I don't have this, here's what I'd
check" or a suggested query and stop there. Go find it. The user has to run
nothing manually; that's the entire point of having web_search. Only fall back
to admitting you don't know AFTER an actual web_search call has come back
empty or unhelpful — and when that happens, say so plainly and name what's
missing rather than writing generic-sounding instructions dressed up as fact.
Guessing at a menu path or field name you don't actually know is fabrication,
worse than no answer at all — but so is naming a query you didn't run.

NEVER claim a write succeeded (write_self_file, create_hpm_task, write_smc_file,
create_tool, any change) unless you actually see that specific tool's own RESULT
message in this conversation confirming it — not your own earlier stated intention
to make the call. A tool-call attempt can silently fail to register (known local
flakiness) and if that happens you'll see no result for it. Caught live
2026-08-14: restart_self() ran successfully but a write_self_file call never
actually executed, and the model still told the user the change was made. If you
don't see a real result confirming a write, say plainly it may not have gone
through and retry, don't narrate success from what you meant to do."""


def run(question: str, model_key: str, max_rounds: int = 10):
    model = MODELS[model_key]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    print(f"NEDA (model: {model})\n", file=sys.stderr)

    for _round_i in range(max_rounds):
        _free_before = vm_free_bytes()
        _round_t0 = time.time()
        resp = ollama.chat(model=model, messages=messages, tools=TOOLS, keep_alive="30m",
                            options={"num_ctx": NUM_CTX})
        log_ollama_call(round_i=_round_i, messages=messages, tools_count=len(TOOLS),
                         num_ctx=NUM_CTX, model=model, free_before=_free_before,
                         free_after=vm_free_bytes(), elapsed_s=time.time() - _round_t0,
                         success=True, source="agent")
        msg = resp["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            tool_calls = _extract_fallback_tool_calls(msg.get("content", ""), set(TOOL_MAP))
            if tool_calls:
                print("  (recovered tool call the model emitted without <tool_call> tags)",
                      file=sys.stderr)
        if not tool_calls:
            print(msg.get("content", ""))
            return

        for call in tool_calls:
            name = call["function"]["name"]
            args = call["function"]["arguments"]
            print(f"  [tool call] {name}({args})", file=sys.stderr)
            fn = TOOL_MAP.get(name)
            if fn is None:
                result = f"error: unknown tool {name!r}"
            else:
                try:
                    result = fn(**args)
                except Exception as e:
                    result = f"error calling {name}: {e}"
            messages.append({"role": "tool", "content": str(result), "name": name})

    print("(stopped after max tool-call rounds without a final answer)", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--model", choices=["coder", "reasoner"], default="coder")
    args = parser.parse_args()
    run(" ".join(args.question), args.model)

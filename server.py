#!/usr/bin/env python3
"""NEDA — local web chat UI. Merges RAG retrieval (memory files, Pine scripts,
and crawled HPM documentation) with live tool access, served as a streaming chat
interface. Runs entirely locally — Ollama + chromadb, no Claude tokens involved
in serving requests.

Tool access is read-only for HPM and Pine Script, with two deliberate exceptions:
full run/read/write access to the SMC Structure Scanner (smc_tools.py) and to
NEDA's own source code (self_tools.py, incl. restart_self), each scoped to its
own directory, per explicit user instruction (2026-08-14) that NEDA should be
able to run/modify the scanner and inspect/improve itself without going through
Claude.

Usage: python3 server.py [--port 8766]
"""
import argparse
import ast
import inspect
import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

import chromadb
import ollama
from flask import Flask, Response, request, send_from_directory

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

LATENCY_LOG = Path.home() / "local-ai" / "logs" / "latency.jsonl"

# Request-scoped cancellation flags. Each chat request gets its own Event so
# Stop can cancel one request without restarting NEDA or affecting other users.
_CANCEL_LOCK = threading.Lock()
_CANCEL_EVENTS = {}


def _new_cancel_event(request_id):
    event = threading.Event()
    with _CANCEL_LOCK:
        _CANCEL_EVENTS[request_id] = event
    return event


def _cancel_request(request_id):
    with _CANCEL_LOCK:
        event = _CANCEL_EVENTS.get(request_id)
        if event is None:
            return False
        event.set()
        return True


def _remove_cancel_event(request_id):
    with _CANCEL_LOCK:
        _CANCEL_EVENTS.pop(request_id, None)




def _log_latency(model_key, question, elapsed_s, rounds, tool_calls, hit_count):
    LATENCY_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.time(), "model": model_key, "q_chars": len(question),
             "elapsed_s": round(elapsed_s, 2), "rounds": rounds,
             "tool_calls": tool_calls, "retrieval_hits": hit_count}
    with LATENCY_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")

DB_DIR = "/Users/abchatur/local-ai/chroma_db"
EMBED_MODEL = "nomic-embed-text"
COLLECTIONS = ["knowledge", "hpm_docs", "innovation_suite_docs"]
TOP_K = 6
# L2 distance cutoff (chromadb default space) — measured empirically: genuinely
# relevant hits score ~200-330, unrelated ones 340-470+. Anything worse than this
# is noise that misleads more than it helps, so drop it rather than pad context.
MAX_DISTANCE = 330
KEEP_ALIVE = "30m"  # keep models resident between chat turns to avoid reload stalls

# Dedicated client with a hard read timeout. The bare module-level ollama.chat()
# has none — when the Ollama daemon wedges (caught live twice on 2026-08-14,
# both times a multi-tool-call turn stalled the daemon connection at 0% CPU with
# no error, no progress, indefinitely), that call blocks the request thread
# forever with no way to recover short of restarting the whole server. 120s was
# comfortably above the 55-75s single-round times seen in logs/latency.jsonl for
# small payloads, but a round immediately after a large tool result (e.g.
# read_self_file on a real source file, ~13KB/3-4K tokens on top of the system
# prompt + 25 tool schemas + retrieval context) legitimately needs more —
# confirmed live 2026-08-14 hitting this ceiling repeatedly on exactly that
# round even on a warm model. Bumped to 240s so a genuinely slow round isn't
# mistaken for a wedge; a TRUE wedge (0% CPU, no progress at all) still gets
# caught, just later.
_ollama = ollama.Client(timeout=240.0)

MODELS = {
    "coder": "qwen2.5-coder:32b",
    "reasoner": "deepseek-r1:32b",
    "vision": "qwen2.5vl:7b",
}

# No PARAMETER num_ctx is set on any of these Modelfiles, so Ollama defaults to
# the model's full advertised context (32768 for qwen2.5-coder:32b) regardless
# of what a given request actually needs — that reserves a large KV cache
# unconditionally. Confirmed live 2026-08-14: base weights are 19GB on disk but
# the running process RSS was 26.3GB, a ~7GB gap that's exactly this
# reservation. On this machine (36GB total RAM), that left ~64MB free at idle
# with heavy ongoing swap I/O — any request that grows the KV cache further
# (e.g. a large read_self_file result folded back into context) pushed the
# process into disk-swapped memory access, which is 100-1000x slower than RAM
# and presents as an indefinite hang (near-0% CPU) rather than a normal slow
# response. Reproduced 6+ times, independent of Flask/daemon freshness/tools
# schema presence — this was a genuine hardware capacity issue, not a bug.
# 16384 comfortably covers the real worst case (system prompt ~2K tokens +
# ~25 tool schemas + a large single-file read ~3-4K tokens + retrieval context
# a few K tokens) while roughly halving the fixed KV-cache reservation.
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
    print(f"[custom_tools] {_line}")

TOOL_MAP = {t.__name__: t for t in TOOLS}

# Targeted NEDA self-edits deliberately use a small toolset.
# This prevents the 32B model from receiving unrelated HPM/Pine/web
# tool schemas and RAG context when modifying its own code.
SELF_EDIT_TOOL_NAMES = {
    "list_self_files",
    "search_self_code",
    "read_self_range",
    "apply_self_patch",
    "restart_self",
    "self_status",
}

SELF_EDIT_TOOLS = [
    t for t in TOOLS
    if t.__name__ in SELF_EDIT_TOOL_NAMES
]


def _is_self_edit_request(question):
    q = (question or "").lower()

    self_reference = (
        "neda" in q
        or "your " in q
        or "yourself" in q
        or "this system" in q
        or "your code" in q
        or "your chat" in q
        or "your interface" in q
    )

    edit_intent = any(word in q for word in (
        "edit",
        "change",
        "modify",
        "update",
        "fix",
        "improve",
        "add",
        "remove",
        "replace",
        "rename",
        "patch",
    ))

    return self_reference and edit_intent


SYSTEM_PROMPT = """You are NEDA, a local assistant specialized in four domains:
1. BMC Helix / Innovation Studio / HPM (Agility Suite) — you have both indexed
   documentation and live read-only tool access (query_hpm_tasks, get_hpm_task)
   to current task data, PLUS one deliberate write exception added 2026-08-14:
   create_hpm_task creates a new Project Task under the existing "BMC Helix
   26.3 Rollout" project, as a child of a task you name by summary text. This
   is the ONLY HPM write you can do — you cannot create a Project, Team,
   Person, or top-level category, cannot delete anything, cannot change an
   existing task's status, and cannot touch any other project. Root Status /
   Root Status Reason records are a confirmed hard backend read-only block
   (returns "record is read only" no matter what) — don't attempt to create
   those even if asked, say plainly that HPM itself blocks it. Before calling
   create_hpm_task, confirm in your reply what you're about to create (summary,
   parent, assignee if any) — same "explain before acting" rule as every other
   write tool you have.
2. Pine Script (TradingView) and the user's trading strategies.
3. The SMC Structure Scanner (~/kite-test/apex-lab/local/) — here, unlike (1)
   and (2), you have REAL execute and write access via run_smc_scanner,
   read_smc_file, write_smc_file, and smc_status. You can run it, diagnose it,
   and modify its code directly, by the user's explicit instruction — no need
   to route this through Claude. If scans look wrong or quiet, call
   smc_status() first: the most common failure is the structure-levels cache
   going stale (>72h old), which silently drops every symbol before the scan
   even checks the Kite token — check cache age before assuming it's a
   credentials problem. Never touch .kite_config or .kite_token (both tools
   refuse this anyway), and never call run_smc_scanner with "watch" (loops
   forever, would hang) or "serve" (already running permanently on port 8765
   — a second one just port-conflicts). Before writing a code change with
   write_smc_file, explain the change first.
4. YOURSELF (~/local-ai/) — list_self_files, read_self_file, write_self_file,
   restart_self, self_status. MANDATORY for TWO request shapes: (a)
   introspection ("how do you work", performance, architecture) and (b)
   action/feature requests where "you"/"your" means THIS system, e.g. "add X
   to your chat bar" = edit web/index.html, not a web_search about how Zoom/
   Slack do it. Past failure (2026-08-14): "enable drag and drop in your chat
   bar" got answered from Zoom/OpenAI help articles because "your" wasn't
   recognized as self-reference — no self_tools call was ever made. Rule: if
   "you/your" points at this system, call self_tools first, don't web_search.
   Never answer self-questions from retrieved context or generic knowledge —
   a past run fabricated an answer from an unrelated BMC doc that happened to
   contain matching keywords.

   EDITING YOURSELF (2026-08-14, revised): for ANY targeted change to your own
   code, PREFER search_self_code -> read_self_range -> apply_self_patch over
   write_self_file. This is not a style preference — write_self_file requires
   holding the ENTIRE file in your context for a full read-then-write round
   trip, and on this machine that has repeatedly caused multi-minute hangs or
   outright timeouts on files as small as 9-14KB (a real hardware memory
   limit, not a bug — see project_local_ai_neda.md if asked to explain why).
   apply_self_patch never needs the whole file in your context: it reads the
   real file from disk itself, finds your exact `old` text, and writes the
   replacement — you only hold the small old/new snippets, not the file
   around them. Workflow: search_self_code(query) to find the right file and
   line, read_self_range(file, start, end) to see a SMALL window around it
   (never the whole file), then apply_self_patch(file, old, new) with `old`
   copied verbatim from what you just read. apply_self_patch tells you
   exactly why it refused (0 matches, ambiguous match, syntax error, or the
   same >50%-shrink guard write_self_file has) — fix and retry rather than
   falling back to write_self_file out of impatience. Reserve write_self_file
   for a genuinely new file's worth of content or a restructuring too broad
   for one patch. Either way, restart_self() is required after, or you keep
   running the old code — say so in your reply.

   SELF-IMPROVEMENT, extended 2026-08-14: you can genuinely grow your own
   capability, not just inspect it. create_tool(filename, code) writes a
   brand-new tool file to custom_tools/ — every top-level function with a
   proper docstring in it becomes a real, callable tool the next time you
   start (list_custom_tools() shows what loaded). remember(note, tag) and
   recall_notes(tag) are your own persistent notes, separate from the
   retrieved knowledge base — call reindex_knowledge() afterward so a new
   note is actually searchable. pip_install(package) installs one exact
   package into your own venv for a tool that needs a library you don't have
   — it refuses this codebase's own core dependencies (ollama, chromadb,
   flask, kiteconnect, pandas, numpy, beautifulsoup4) to protect the process
   you run in. Always explain what you're about to build/install and why
   BEFORE calling create_tool or pip_install, same rule as write_self_file.
   Always call restart_self() after create_tool() — it's not live until then.

   CLOSING CAPABILITY GAPS (2026-08-14): when a tool comes back saying it
   can't do something, or you realize partway through a task that nothing in
   your toolset covers what's needed, that is a gap to CLOSE, not a
   limitation to describe and stop at. Work the loop: (1) web_search for how
   to actually do the specific missing thing in Python — the real library,
   the real approach; (2) web_fetch one promising doc/example page if the
   search snippets alone aren't enough to write real code; (3) pip_install
   any library the approach needs, if you don't have it yet; (4) create_tool
   with REAL logic based on what you actually found — not a stub, not a
   comment describing what it would do (create_tool rejects those outright,
   see its own docstring for why); (5) restart_self() so it loads; (6) in
   your final answer, say plainly what you built and why. Only fall back to
   "I can't do this" if you've actually tried this loop and hit a real wall
   (e.g. the thing genuinely needs credentials/access you don't have, or a
   local binary that can't be pip-installed) — and when that happens, name
   the specific wall, don't just restate that you lack the capability.
   Two real, permanent limits worth knowing before you start: you have no
   real browser session (web_fetch_rendered opens a fresh, logged-out
   browser every time — see its docstring), and pip_install only accepts a
   single bare package name (no install scripts, no downloading separate
   binaries) — some capabilities genuinely need a human, and recognizing
   that honestly is not the same failure as not trying at all.

Context retrieved from the local knowledge base may be included below — use it
when relevant. You also have tools for live HPM lookups and reading Pine scripts;
use them when the question needs current data rather than static documentation.
You also have web_search and web_fetch for live internet access. Don't reach
for the web for questions the local knowledge base or tools already answer —
but whenever they DON'T, you must call web_search yourself before replying.
This is MANDATORY, NOT OPTIONAL: never respond with "I don't have this, here's
what I'd check" or a suggested query and stop there — the user should never
have to run a search manually, that's what web_search is for. Only fall back
to admitting you don't know AFTER an actual web_search call has come back
empty or unhelpful.
When you do search the web: call web_search ONCE, then answer directly from the
titles/snippets you get back. Only call web_fetch if you genuinely need the full
page content the snippets don't cover, and only for one specific promising URL —
don't retry web_search with rephrased queries or fetch multiple URLs hoping for
a better answer. Give your best answer from what you have rather than looping.
If web_fetch comes back basically empty on an obvious JS-driven app (a bare
shell, "Loading...", "Hash Handler", an empty <div id="app">), that's a plain
HTTP GET hitting a client-rendered page — retry the SAME url with
web_fetch_rendered, which runs a real headless browser so the page's JS
actually executes, instead of concluding you can't do it and describing the
limitation to the user. Its one real limit: it opens a fresh, logged-out
browser every time, so it can't see anything behind a login wall — if the
rendered page turns out to be a login screen, say that plainly, don't present
it as the real content.
For Pine Script you have READ-ONLY access — you cannot edit files there. For HPM
you're read-only EXCEPT for create_hpm_task (described above) — that one specific
write is real, everything else about HPM (editing an existing task, changing
status, creating Projects/Teams/People) is still read-only. If asked for an HPM
change outside what create_hpm_task covers, or a Pine Script edit, say plainly
that it needs to go through Claude instead. The SMC Structure Scanner is the
other exception, described above.

Generation is slow on this hardware (~7 tokens/sec) — every extra sentence has a
real, noticeable latency cost for the user. Be concise: answer directly, skip
preamble ("Great question!", restating the question), skip padding sentences that
don't add information, and stop once the question is answered rather than adding
extra caveats or elaboration nobody asked for. When calling query_hpm_tasks, pass
assignee_name whenever a specific person is named or implied — an unscoped call
returns only a capped sample, not the full list, so don't rely on it for a
complete picture unless the question truly needs a broad, unscoped view.

Never invent plausible-sounding steps. If retrieval doesn't contain the answer,
call web_search yourself first — do not skip straight to "I don't have real
information on this, here's what I'd check" with a suggested query; that is
now the wrong response unless you already tried searching and it came back
empty. Only after an actual web_search call fails to turn up the answer should
you say so directly and name what's missing (e.g. "no doc page or search
result covers this specific field"). Do not write generic BMC-sounding
instructions dressed up as fact ("navigate to Settings, look for a section
related to X, click New") when you don't actually know the real menu path or
field name — that is fabrication, worse than no answer at all.

NEVER claim a write succeeded (write_self_file, create_hpm_task, write_smc_file,
create_tool, any change) unless you actually see that specific tool's own RESULT
message in this conversation confirming it — not your own earlier stated intention
to make the call, not a memory of having "just done" it. Your own tool-call attempt
can silently fail to register (a known local flakiness — sometimes what you emit
doesn't reach the real tool-calling mechanism at all) and if that happens you will
see NO result for it, only for whatever else you called. Caught live 2026-08-14:
asked to add a clear-chat button, the model called restart_self() successfully but
its write_self_file call never actually executed (no result for it ever appeared)
— and still told the user the change was made. If you don't see a real result
confirming a write, say plainly that it may not have gone through and retry the
call, don't narrate success from what you meant to do."""

_TOOL_CALL_RE = re.compile(
    r"(?:<tool_call>\s*)?(\{\s*\"name\"\s*:\s*\"(\w+)\"\s*,\s*\"arguments\"\s*:\s*(\{.*?\})\s*\})(?:\s*</tool_call>)?",
    re.DOTALL,
)

# Second fallback (added 2026-08-14): sometimes the model emits neither JSON form
# above, just a bare Python-style call like "self_status()" as plain text — caught
# live testing self_tools.py, the call was silently dropped and printed as if it
# were the final answer. Only matches known tool names, only zero-arg/single-
# string-arg calls (covers every real tool here).
_BARE_CALL_RE = re.compile(r"\b(\w+)\(\s*(?:[\"']([^\"']*)[\"'])?\s*\)|^(\w+)\s+(.+)$")


def _extract_fallback_tool_calls(content, known_names=None):
    if not content:
        return []
    calls = []
    for _, name, args_json in _TOOL_CALL_RE.findall(content):
        try:
            # strict=False: a bare-text tool-call emission (this whole function
            # only runs when the model didn't use the real tool_calls API field)
            # commonly contains literal newlines inside a multi-line string
            # argument — e.g. write_self_file's HTML/JS content — instead of
            # properly escaped \n. Strict JSON rejects that as a bad control
            # character and the call vanishes silently, at which point the
            # model has no idea its own write never happened and narrates a
            # false success in the next round. Caught live 2026-08-14: exactly
            # this, on a write_self_file call for web/index.html.
            args = json.loads(args_json, strict=False)
        except json.JSONDecodeError:
            # Second recovery tier (caught live 2026-08-14, a DIFFERENT
            # malformation than the one above): the model sometimes uses
            # single-quoted string values for a bare tool call's arguments
            # instead of JSON's required double quotes — e.g.
            # {"filename": "x", "old": '<button>...', "new": '<button>...'}.
            # This isn't a strictness issue json.loads can be told to
            # tolerate — single-quoted strings are invalid JSON syntax, full
            # stop. But it IS valid Python literal syntax (Python allows
            # mixed ' and " within one literal), so ast.literal_eval parses
            # it correctly. Confirmed live: this exact malformed payload
            # (an apply_self_patch call whose old/new values used single
            # quotes) silently vanished under json.loads alone — the model
            # never got an error, never retried, and told the user a fix
            # was applied when nothing had actually changed on disk.
            try:
                args = ast.literal_eval(args_json)
                if not isinstance(args, dict):
                    continue
            except (ValueError, SyntaxError):
                continue
        calls.append({"function": {"name": name, "arguments": args}})
    if not calls and known_names:
        # _BARE_CALL_RE now has 4 capture groups (2 per alternative — see the
        # regex definition above), so findall returns 4-tuples; exactly one
        # pair is non-empty depending on which alternative matched. A prior
        # patch (2026-08-14) added the second alternative but left this loop
        # unpacking 2 values — a real regression caught immediately after
        # applying: it would have raised ValueError on EVERY bare-call match,
        # including the paren-style form that worked fine before. Also fixes
        # a pre-existing bug in the same pass: the argument key was always
        # hardcoded to "filename", which is wrong for any tool whose first
        # parameter is named differently (e.g. web_search's is `query`) —
        # now looked up via the matched tool's real signature instead.
        for paren_name, paren_arg, bare_name, bare_arg in _BARE_CALL_RE.findall(content):
            name = paren_name or bare_name
            arg = paren_arg or bare_arg
            if not name or name not in known_names:
                continue
            if arg:
                fn = TOOL_MAP.get(name)
                params = list(inspect.signature(fn).parameters) if fn else []
                key = params[0] if params else "filename"
                args = {key: arg}
            else:
                args = {}
            calls.append({"function": {"name": name, "arguments": args}})
    return calls


def _needs_normal_tools(question: str) -> bool:
    """Return True when a normal request genuinely needs live tools."""
    q = question.lower().strip()

    web_markers = (
        "search the web", "search online", "look up", "browse",
        "latest", "today", "currently", "current", "recent", "news",
        "price", "stock price", "share price", "weather",
        "exchange rate", "live", "real-time", "what happened",
        "this week", "this month", "as of now",
    )

    domain_markers = (
        "hpm", "helix portfolio", "project task", "pine script",
        "tradingview", "smc scanner", "structure scanner", "kite",
        "remember this", "remember that", "what do you remember",
        "recall", "learn this",
    )

    action_markers = (
        "find ", "fetch ", "retrieve ", "check ", "inspect ",
        "read ", "list ", "run ", "execute ", "create ", "update ",
        "delete ", "write ", "analyze my ", "look in ",
    )

    return any(
        marker in q
        for marker in web_markers + domain_markers + action_markers
    )


def retrieve(query, k=TOP_K):
    client = chromadb.PersistentClient(path=DB_DIR)
    emb = _ollama.embeddings(model=EMBED_MODEL, prompt=query, keep_alive=KEEP_ALIVE)["embedding"]
    hits = []
    for name in COLLECTIONS:
        try:
            collection = client.get_collection(name)
        except Exception:
            continue
        results = collection.query(query_embeddings=[emb], n_results=k, include=["documents", "metadatas", "distances"])
        for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            if dist <= MAX_DISTANCE:
                hits.append((doc, meta, dist))
    hits.sort(key=lambda h: h[2])
    return [(doc, meta) for doc, meta, _ in hits[: k * 2]]  # cap the combined pool


def _delayed_restart():
    """Kill and relaunch com.neda.server ~1s from now, in a detached subprocess
    so it survives this process dying. The delay gives the current SSE response
    time to actually flush over the socket before launchd SIGKILLs this process."""
    import os
    import subprocess
    uid = os.getuid()
    subprocess.Popen(
        ["bash", "-c", f"sleep 1 && launchctl kickstart -k gui/{uid}/com.neda.server"],
        start_new_session=True,
    )


app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/cancel/<request_id>", methods=["POST"])
def cancel(request_id):
    cancelled = _cancel_request(request_id)
    return {"ok": True, "cancelled": cancelled}


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json()
    question = body["question"]
    model_key = body.get("model", "coder")
    image_b64 = body.get("image")  # data-URL-stripped base64, or None
    request_id = body.get("request_id") or uuid.uuid4().hex
    cancel_event = _new_cancel_event(request_id)

    def sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    # Vision path: an image forces the vision model, single-turn (no tool-calling —
    # qwen2.5vl isn't reliable at combining tool use with image understanding, and
    # a screenshot question rarely needs a live HPM/Pine lookup anyway).
    if image_b64:
        def vision_stream():
            yield sse("thinking", {})
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question or "What's in this screenshot?",
                 "images": [image_b64]},
            ]
            stream = _ollama.chat(model=MODELS["vision"], messages=messages, stream=True, keep_alive=KEEP_ALIVE,
                                   options={"num_ctx": NUM_CTX})
            first = True
            for chunk in stream:
                if first:
                    yield sse("thinking_done", {})
                    first = False
                yield sse("token", {"text": chunk["message"]["content"]})
            yield sse("done", {})
        return Response(vision_stream(), mimetype="text/event-stream")

    model = MODELS[model_key]

    def stream():
        t0 = time.time()
        total_tool_calls = 0
        pending_restart = False
        yield sse("thinking", {})
        self_edit = _is_self_edit_request(question)

        if self_edit:
            # Self-edits operate directly on ~/local-ai/.
            # Do not add unrelated RAG material to the model context.
            hits = []
            sources = []
            active_tools = SELF_EDIT_TOOLS
            request_num_ctx = 8192

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content":
                    "This is a NEDA self-edit request. Work directly on "
                    "NEDA's own source under ~/local-ai/. "
                    "Use search_self_code and read_self_range to locate "
                    "the relevant code, then prefer apply_self_patch for "
                    "the smallest targeted change. Do not use "
                    "write_self_file for a targeted change.\n\n"
                    f"Question: {question}"},
            ]

        else:
            hits = retrieve(question)
            sources = sorted(set(m["source"] for _, m in hits))

            # Fast path: ordinary questions don't need tool schemas.
            # This prevents Qwen from inventing an unnecessary tool call.
            needs_tools = _needs_normal_tools(question)
            active_tools = TOOLS if needs_tools else []
            request_num_ctx = NUM_CTX

            context = "\n\n---\n\n".join(
                f"[{m['source']}]\n{d}" for d, m in hits
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content":
                    f"Context from local knowledge base:\n\n{context}"
                    f"\n\n---\n\nQuestion: {question}"},
            ]

        yield sse("retrieval", {"sources": sources})

        for round_i in range(10):  # was 6 — a research-then-build chain (web_search,
                                    # web_fetch, create_tool, pip_install, restart_self,
                                    # final answer) genuinely needs more room than a
                                    # simple lookup does
            if round_i > 0:
                yield sse("thinking", {})  # another model pass needed after a tool result
            _round_t0 = time.time()
            _free_before = vm_free_bytes()
            try:
                response_stream = _ollama.chat(
                    model=model,
                    messages=messages,
                    tools=active_tools,
                    stream=True,
                    keep_alive=KEEP_ALIVE,
                    options={"num_ctx": request_num_ctx},
                )

                content_parts = []
                streamed_tool_calls = []

                for chunk in response_stream:
                    if cancel_event.is_set():
                        return

                    chunk_message = chunk.get("message", {})
                    content = chunk_message.get("content", "")
                    if content:
                        content_parts.append(content)

                    chunk_tool_calls = chunk_message.get("tool_calls") or []
                    if chunk_tool_calls:
                        streamed_tool_calls.extend(chunk_tool_calls)

                if cancel_event.is_set():
                    return

                resp = {
                    "message": {
                        "role": "assistant",
                        "content": "".join(content_parts),
                    }
                }

                if streamed_tool_calls:
                    resp["message"]["tool_calls"] = streamed_tool_calls
            except Exception as e:
                log_ollama_call(
                    round_i=round_i,
                    messages=messages,
                    tools_count=len(active_tools),
                    num_ctx=request_num_ctx,
                    model=model,
                    free_before=_free_before,
                    free_after=vm_free_bytes(),
                    elapsed_s=time.time() - _round_t0,
                    success=False,
                    error=str(e),
                    source="server",
                )
                yield sse("error", {"text": f"Ollama didn't respond within 240s ({e}). "
                                             "The daemon may be wedged — try again in a moment; "
                                             "restarting Ollama.app may be needed if this repeats."})
                _log_latency(model_key, question, time.time() - t0, round_i + 1,
                             total_tool_calls, len(hits))
                return
            log_ollama_call(
                round_i=round_i,
                messages=messages,
                tools_count=len(active_tools),
                num_ctx=request_num_ctx,
                model=model,
                free_before=_free_before,
                free_after=vm_free_bytes(),
                elapsed_s=time.time() - _round_t0,
                success=True,
                source="server",
            )
            msg = resp["message"]
            messages.append(msg)

            tool_calls = (
                msg.get("tool_calls")
                or _extract_fallback_tool_calls(
                    msg.get("content", ""),
                    {t.__name__ for t in active_tools},
                )
            )
            yield sse("thinking_done", {})
            if not tool_calls:
                # final answer — stream it token by token for a live-typing feel
                text = msg.get("content", "")
                for i in range(0, len(text), 20):
                    yield sse("token", {"text": text[i:i + 20]})
                yield sse("done", {})
                _log_latency(model_key, question, time.time() - t0, round_i + 1,
                             total_tool_calls, len(hits))
                if pending_restart:
                    _delayed_restart()
                return

            for call in tool_calls:
                if cancel_event.is_set():
                    return
                total_tool_calls += 1
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                yield sse("tool_call", {"name": name, "args": args})
                try:
                    with (Path.home() / "local-ai" / "logs" / "tool_trace.log").open("a") as trace:
                        trace.write(json.dumps({
                            "ts": time.time(),
                            "request_id": request_id,
                            "round": round_i,
                            "tool": name,
                            "args": args,
                            "question": question,
                        }) + "\\n")
                except Exception:
                    pass
                if name == "restart_self":
                    # Do NOT actually kill the process here — this generator IS the
                    # process handling the current response. Running the real
                    # `launchctl kickstart -k` inline killed the server mid-stream
                    # before "done" ever reached the browser, leaving the UI stuck
                    # forever with no error shown (caught live 2026-08-14). Instead,
                    # note the request and defer the real kill until after this
                    # response has fully streamed back to the client.
                    pending_restart = True
                    result = ("restart queued — it will happen automatically right "
                               "after this response finishes sending, no need to "
                               "call restart_self again")
                else:
                    fn = TOOL_MAP.get(name)
                    try:
                        result = fn(**args) if fn else f"error: unknown tool {name!r}"
                    except Exception as e:
                        result = f"error calling {name}: {e}"
                messages.append({"role": "tool", "content": str(result), "name": name})

        yield sse("token", {"text": "(stopped after max tool-call rounds without a final answer)"})
        yield sse("done", {})
        _log_latency(model_key, question, time.time() - t0, 10, total_tool_calls, len(hits))
        if pending_restart:
            _delayed_restart()

    def cleanup_stream():
        try:
            yield from stream()
        finally:
            _remove_cancel_event(request_id)

    return Response(cleanup_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    print(f"NEDA serving on http://localhost:{args.port}")
    app.run(host="127.0.0.1", port=args.port, threaded=True)

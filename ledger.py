#!/usr/bin/env python3
"""Running ledger of tasks Claude has done and their estimated token cost, plus
routing decisions (local model vs self) and estimated savings from those.

Every number in here is Claude's own ESTIMATE at logging time, not measured
ground truth — there is no exact token-accounting API for Claude's own turns.
Always reported as estimates, never as precise measurements.

Usage:
  # A task handled directly (not routed) — just its cost:
  ./ledger.py log --task "..." --cost 4000

  # A task routed to the local model, with the counterfactual self-cost:
  ./ledger.py log --task "..." --cost 600 --routed --self-cost 2500

  # A task not routed on purpose (write/judgment/etc), for the record:
  ./ledger.py log --task "..." --cost 4000 --reason "requires a write"

  ./ledger.py report
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path.home() / "local-ai" / "token_ledger.jsonl"


def log(args):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": args.task,
        "routed": args.routed,
        "cost_est": args.cost,
    }
    if args.routed:
        entry["self_cost_est"] = args.self_cost
        entry["savings_est"] = (args.self_cost or 0) - args.cost
    if args.reason:
        entry["reason"] = args.reason
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    tail = f" savings_est={entry['savings_est']:,}" if args.routed else ""
    print(f"logged: \"{args.task}\" cost_est={args.cost:,}{tail}")


def report(args):
    if not LEDGER.exists():
        print("no ledger entries yet")
        return
    entries = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    routed = [e for e in entries if e["routed"]]
    direct = [e for e in entries if not e["routed"]]
    total_cost = sum(e.get("cost_est", 0) for e in entries)
    total_savings = sum(e.get("savings_est", 0) for e in routed)
    total_self_cost_of_routed = sum(e.get("self_cost_est", 0) for e in routed)

    print(f"Total tasks logged: {len(entries)}")
    print(f"  Routed to local model: {len(routed)}")
    print(f"  Handled directly:      {len(direct)}")
    print()
    print(f"Total estimated tokens spent (actual, across all tasks): {total_cost:,}")
    if routed:
        pct = (total_savings / total_self_cost_of_routed * 100) if total_self_cost_of_routed else 0
        print(f"Total estimated tokens SAVED by routing: {total_savings:,} "
              f"(~{pct:.0f}% reduction on those {len(routed)} tasks vs. doing them directly)")
    print()
    print("Tasks, most recent first:")
    for e in reversed(entries):
        tag = "routed " if e["routed"] else "direct "
        sav = f"  (saved ~{e.get('savings_est', 0):,})" if e["routed"] else ""
        print(f"  [{tag}] {e.get('cost_est', 0):>7,} tok  {e['task']}{sav}")
    print()
    print("Note: all figures are Claude's own estimates made at logging time, not")
    print("measured ground truth — no exact token-accounting API exists for this.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("log")
    lg.add_argument("--task", required=True)
    lg.add_argument("--cost", type=int, required=True, help="estimated tokens this task actually cost")
    lg.add_argument("--routed", action="store_true", help="was this routed to the local model?")
    lg.add_argument("--self-cost", type=int, default=0, help="if routed: estimated cost had it been done directly")
    lg.add_argument("--reason", default="", help="optional note, e.g. why not routed")
    lg.set_defaults(func=log)

    rp = sub.add_parser("report")
    rp.set_defaults(func=report)

    args = parser.parse_args()
    args.func(args)

#!/usr/bin/env python3
"""Command line for the improvement loop (issue #3, section 6).

Usage:
    loop.py triage RUN_DIR [--sandbox SANDBOX.json] [--json OUT] [--markdown OUT]
    loop.py decide CONTROL_RUN ARM_RUN... --targets SPEC... [--margin M] [--token-budget B] [--token-cap N]
    loop.py ledger append ENTRY.json|- [--ledger PATH]
    loop.py ledger history ARTIFACT [--ledger PATH]
    loop.py holdout status --harness-version V [--state PATH] [--ledger PATH]
    loop.py holdout checkpoint TIP_RUN CANDIDATE_RUN --harness-version V [--force] [--state PATH] [--ledger PATH]

A run directory holds `run.json` and `sessions.jsonl` (records.py). A target SPEC is `cluster:NAME` (or a bare
NAME), `domain:NAME` or `cases:ID,ID`, one per arm in order. SANDBOX.json maps case id to sandbox kind.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import decide
import holdout
import triage
from ledger import DEFAULT_PATH, Ledger


def _write(text: str, path: Path | None) -> None:
    if path is None:
        sys.stdout.write(text)
    else:
        path.write_text(text)


def cmd_triage(args: argparse.Namespace) -> int:
    run = decide.Run.load(args.run)
    sandbox = json.loads(args.sandbox.read_text()) if args.sandbox else None
    result = triage.triage(run.records, sandbox=sandbox)
    if args.json:
        args.json.write_text(result.to_json())
    _write(result.to_markdown(), args.markdown)
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    control = decide.Run.load(args.control)
    arms = [decide.Run.load(path) for path in args.arms]
    if len(args.targets) != len(arms):
        raise SystemExit(f"--targets needs one spec per arm: {len(arms)} arms, {len(args.targets)} specs")
    targets = [decide.resolve_target(spec, control.records) for spec in args.targets]
    rule = decide.Rule(margin=args.margin, token_budget=args.token_budget, token_cap=args.token_cap)
    results = decide.decide(control, arms, targets, rule)
    if args.json:
        args.json.write_text(json.dumps([r.to_dict(rule.alpha) for r in results], indent=2, sort_keys=True))
    _write(decide.to_markdown(results), args.markdown)
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    if args.action == "append":
        text = sys.stdin.read() if args.value == "-" else Path(args.value).read_text()
        print(json.dumps(ledger.append(json.loads(text)), sort_keys=True))
    else:
        for entry in ledger.history(args.value):
            print(json.dumps(entry, sort_keys=True))
    return 0


def cmd_holdout(args: argparse.Namespace) -> int:
    entries = Ledger(args.ledger).entries()
    if args.action == "status":
        current = holdout.status(args.state, entries, args.harness_version)
        stop, reason = holdout.stop_condition(entries, current["checkpoints"])
        print(json.dumps({**current, "stop": stop, "stop_reason": reason}, indent=2, sort_keys=True))
        return 0
    if len(args.runs) != 2:
        raise SystemExit("holdout checkpoint needs TIP_RUN and CANDIDATE_RUN")
    tip, candidate = (decide.Run.load(path) for path in args.runs)
    try:
        result = holdout.checkpoint(args.state, entries, args.harness_version, tip, candidate, force=args.force)
    except (holdout.BudgetExhausted, holdout.NotDue) as exc:
        print(f"holdout: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="command", required=True)

    p = sub.add_parser("triage", help="label failures, rank suspicious artifacts, cluster")
    p.add_argument("run", type=Path)
    p.add_argument("--sandbox", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--markdown", type=Path)
    p.set_defaults(func=cmd_triage)

    p = sub.add_parser("decide", help="apply the pre-registered accept rule")
    p.add_argument("control", type=Path)
    p.add_argument("arms", type=Path, nargs="+")
    p.add_argument("--targets", nargs="+", required=True)
    p.add_argument("--margin", type=float, default=decide.Rule.margin)
    p.add_argument("--token-budget", type=float, default=decide.Rule.token_budget)
    p.add_argument("--token-cap", type=float)
    p.add_argument("--json", type=Path)
    p.add_argument("--markdown", type=Path)
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("ledger", help="append to or query the experiment ledger")
    p.add_argument("action", choices=["append", "history"])
    p.add_argument("value", help="ENTRY.json or - for append, ARTIFACT (kind:name) for history")
    p.add_argument("--ledger", type=Path, default=DEFAULT_PATH)
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("holdout", help="holdout read budget and checkpoints")
    p.add_argument("action", choices=["status", "checkpoint"])
    p.add_argument("runs", type=Path, nargs="*", help="TIP_RUN CANDIDATE_RUN for checkpoint")
    p.add_argument("--harness-version", required=True)
    p.add_argument("--force", action="store_true", help="checkpoint before it is due (still counts against the cap)")
    p.add_argument("--state", type=Path, default=holdout.DEFAULT_STATE)
    p.add_argument("--ledger", type=Path, default=DEFAULT_PATH)
    p.set_defaults(func=cmd_holdout)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"loop {args.command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

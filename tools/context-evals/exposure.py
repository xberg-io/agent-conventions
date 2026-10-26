#!/usr/bin/env python3
"""Static start-context report for ai-rulez consumers (issue #3, section 5.1).

Reads the files `ai-rulez generate` wrote in a consumer checkout and reports, per preset, what a session
sees at start: instruction files, unconditional rules, skill and agent listings, MCP servers. It then
checks the always-visible text against domains.toml for leaked domain terms and long descriptions.

Usage:
    exposure.py REPO [REPO ...] [--domains domains.toml] [--json out.json] [--markdown out.md]

Run `ai-rulez generate` in each REPO first. Exit status is 1 when --fail-on-leak is set and a leak
remains outside the accept list.
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import subprocess
import sys
import threading
import time
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

BYTES_PER_TOKEN = 3.9
DESCRIPTION_LIMIT = 250
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class Item:
    kind: str
    name: str
    path: str
    bytes: int
    gated: bool = False
    user_only: bool = False
    description: str = ""


@dataclass
class Leak:
    domain: str
    term: str
    artifact: str
    count: int


@dataclass
class PresetReport:
    repo: str
    preset: str
    items: list[Item] = field(default_factory=list)
    leaks: list[Leak] = field(default_factory=list)
    accepted: list[Leak] = field(default_factory=list)

    def start_bytes(self) -> int:
        # An inlined rule is a section of a root file already counted under "instructions".
        return sum(i.bytes for i in self.items if not i.gated and not i.user_only and i.kind != "inlined-rule")

    def count(self, kind: str) -> int:
        return sum(1 for i in self.items if i.kind == kind)

    def summary(self) -> dict[str, object]:
        listed = [i for i in self.items if i.kind in ("skill", "agent") and not i.gated and not i.user_only]
        return {
            "repo": self.repo,
            "preset": self.preset,
            "start_bytes": self.start_bytes(),
            "start_tokens": round(self.start_bytes() / BYTES_PER_TOKEN),
            "instruction_bytes": sum(i.bytes for i in self.items if i.kind == "instructions"),
            "rules_always": sum(1 for i in self.items if i.kind == "rule" and not i.gated),
            "rules_gated": sum(1 for i in self.items if i.kind == "rule" and i.gated),
            "inlined_rules": sum(1 for i in self.items if i.kind == "inlined-rule"),
            "skills": self.count("skill"),
            "skills_gated": sum(1 for i in self.items if i.kind == "skill" and i.gated),
            "skills_user_only": sum(1 for i in self.items if i.kind == "skill" and i.user_only),
            "agents": self.count("agent"),
            "mcp_servers": self.count("mcp"),
            "mcp_tokens": round(sum(i.bytes for i in self.items if i.kind == "mcp") / BYTES_PER_TOKEN),
            "mcp_unmeasured": sorted(
                i.name for i in self.items if i.kind == "mcp" and not i.description.endswith(" tools")
            ),
            "long_descriptions": sum(1 for i in listed if len(i.description) > DESCRIPTION_LIMIT),
            "listing_bytes": sum(i.bytes for i in listed),
            "leaks": len(self.leaks),
        }


def frontmatter(text: str) -> dict[str, str]:
    """Return the flat `key: value` pairs of a YAML front matter block (no YAML dependency)."""
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    key = None
    for line in match.group(1).splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line[0] in " \t-" and key:
            fields[key] = (fields[key] + " " + line.strip(" -")).strip()
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            fields[key] = value.strip().strip("'\"")
    return fields


def read(path: Path) -> str:
    return COMMENT.sub("", path.read_text(encoding="utf-8", errors="replace"))


def metadata(file: Path) -> dict[str, str]:
    text = file.read_text(encoding="utf-8", errors="replace")
    if file.suffix == ".toml":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return {}
        return {k: str(v) for k, v in data.items() if isinstance(v, str | bool)}
    return frontmatter(text)


def listing(kind: str, directory: Path, repo: Path, pattern: str) -> list[Item]:
    """A skill or agent costs its name and description at start; the body loads on use."""
    items = []
    for file in sorted(directory.glob(pattern)):
        meta = metadata(file)
        name = meta.get("name") or (file.parent.name if kind == "skill" else file.stem)
        description = meta.get("description", "")
        items.append(
            Item(
                kind=kind,
                name=name,
                path=str(file.relative_to(repo)),
                bytes=len(f"- {name}: {description}\n".encode()),
                gated=bool(meta.get("paths") or meta.get("globs")),
                user_only=meta.get("disable-model-invocation", "").lower() == "true",
                description=description,
            )
        )
    return items


def inlined_rules(text: str) -> list[Item]:
    """Split the `## Rules` section of a compact root file into one item per `###` rule."""
    items = []
    section = re.search(r"^## Rules\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    if not section:
        return items
    for block in re.split(r"(?=^### )", section.group(1), flags=re.MULTILINE):
        if block.startswith("### "):
            name = block.splitlines()[0][4:].strip()
            items.append(Item("inlined-rule", name, "AGENTS.md#" + name, len(block.encode())))
    return items


def mcp_servers(path: Path, repo: Path) -> list[Item]:
    """The MCP servers a preset's config declares; they cost nothing here until measure_mcp sizes them."""
    if not path.exists():
        return []
    try:
        if path.suffix == ".toml":
            servers = tomllib.loads(path.read_text()).get("mcp_servers", {})
        else:
            servers = json.loads(path.read_text()).get("mcpServers", {})
    except (json.JSONDecodeError, tomllib.TOMLDecodeError):
        return []
    rel = str(path.relative_to(repo))
    return [Item("mcp", name, rel, 0, description=json.dumps(spec, sort_keys=True)) for name, spec in servers.items()]


def measure_mcp(spec: dict, cwd: Path, timeout: float = 60) -> tuple[int, int]:
    """Start a stdio MCP server, list its tools; return (tool count, bytes of tool schemas and instructions)."""
    command = [spec["command"], *spec.get("args", [])]
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "exposure", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    stdin = "".join(json.dumps(m) + "\n" for m in messages)
    proc = subprocess.Popen(
        command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in iter(proc.stdout.readline, "")], daemon=True).start()
    replies: dict[int, dict] = {}
    try:
        proc.stdin.write(stdin)
        proc.stdin.flush()
        deadline = time.monotonic() + timeout
        while 2 not in replies:
            try:
                message = json.loads(lines.get(timeout=max(0.0, deadline - time.monotonic())))
            except queue.Empty:
                raise RuntimeError(f"MCP server {command[0]!r} gave no tools/list reply within {timeout}s") from None
            if "id" in message:
                replies[message["id"]] = message
    finally:
        proc.kill()
        proc.wait()
        proc.stdin.close()
        proc.stdout.close()
    tools = replies[2].get("result", {}).get("tools", [])
    instructions = (replies.get(1, {}).get("result", {}) or {}).get("instructions") or ""
    size = sum(len(json.dumps(tool, separators=(",", ":"))) for tool in tools) + len(instructions.encode())
    return len(tools), size


def measure_servers(report: PresetReport, repo: Path, names: set[str]) -> None:
    """Size the named servers in place; the rest stay listed as not measured."""
    for item in report.items:
        if item.kind == "mcp" and item.name in names:
            count, size = measure_mcp(json.loads(item.description), repo)
            item.bytes = size
            item.description = f"{count} tools"


def instructions(repo: Path, names: list[str]) -> list[Item]:
    items = []
    for name in names:
        file = repo / name
        if file.exists():
            items.append(Item("instructions", name, name, len(read(file).encode())))
    return items


def claude(repo: Path) -> PresetReport:
    report = PresetReport(repo.name, "claude")
    # Claude Code reads AGENTS.md only through an `@AGENTS.md` import once a CLAUDE.md exists.
    claude_md = repo / "CLAUDE.md"
    names = ["CLAUDE.md"]
    if not claude_md.exists() or "@AGENTS.md" in read(claude_md):
        names.append("AGENTS.md")
    report.items += instructions(repo, names)
    for name in names:
        if (repo / name).exists():
            report.items += inlined_rules(read(repo / name))
    rules = repo / ".claude" / "rules"
    for file in sorted(rules.rglob("*.md")) if rules.exists() else []:
        meta = frontmatter(file.read_text(encoding="utf-8", errors="replace"))
        report.items.append(
            Item("rule", file.stem, str(file.relative_to(repo)), len(read(file).encode()), bool(meta.get("paths")))
        )
    report.items += listing("skill", repo / ".claude" / "skills", repo, "*/SKILL.md")
    report.items += listing("agent", repo / ".claude" / "agents", repo, "*.md")
    report.items += mcp_servers(repo / ".mcp.json", repo)
    return report


def codex(repo: Path) -> PresetReport:
    report = PresetReport(repo.name, "codex")
    report.items += instructions(repo, ["AGENTS.md"])
    agents_md = repo / "AGENTS.md"
    if agents_md.exists():
        report.items += inlined_rules(read(agents_md))
    # Codex does not gate a skill by `paths:`: every skill in the tree is listed at start.
    skills = listing("skill", repo / ".agents" / "skills", repo, "*/SKILL.md")
    for skill in skills:
        skill.gated = False
    report.items += skills
    report.items += listing("agent", repo / ".codex" / "agents", repo, "*.toml")
    report.items += mcp_servers(repo / ".codex" / "config.toml", repo)
    return report


PRESETS = {"claude": claude, "codex": codex}


def always_visible_text(repo: Path, report: PresetReport) -> dict[str, str]:
    """The text each always-visible artifact contributes, keyed by artifact."""
    texts: dict[str, str] = {}
    for item in report.items:
        if item.gated or item.user_only or item.kind == "mcp":
            continue
        if item.kind in ("skill", "agent"):
            texts[f"{item.kind}:{item.name}"] = f"{item.name} {item.description}"
        elif item.kind == "instructions" or item.kind == "rule":
            texts[item.path] = read(repo / item.path)
    return texts


def check_leaks(repo: Path, report: PresetReport, domains: dict, accept: list[dict]) -> None:
    owner = domains.get("repos", {}).get(report.repo, {}).get("domains", [])
    texts = always_visible_text(repo, report)
    for domain, spec in domains.get("domain", {}).items():
        if domain in owner:
            continue
        for term in spec.get("terms", []):
            pattern = re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)
            for artifact, text in texts.items():
                hits = len(pattern.findall(text))
                if not hits:
                    continue
                leak = Leak(domain, term, artifact, hits)
                accepted = any(
                    a.get("term", term) == term
                    and re.fullmatch(a.get("artifact", ".*"), artifact)
                    and re.fullmatch(a.get("repo", ".*"), report.repo)
                    for a in accept
                )
                (report.accepted if accepted else report.leaks).append(leak)


def markdown(reports: list[PresetReport]) -> str:
    rows = [
        (
            "| Repo | Preset | Start tokens | Root file | Inlined rules | Rules always/gated "
            "| Skills (gated, user-only) | Agents | MCP tokens (unmeasured) | Descr. > 250 | Leaks |"
        ),
        "|---|---|---:|---:|---:|---|---|---:|---|---:|---:|",
    ]
    for r in reports:
        s = r.summary()
        rows.append(
            f"| {s['repo']} | {s['preset']} | {s['start_tokens']:,} | {s['instruction_bytes'] / 1024:.1f} KB "
            f"| {s['inlined_rules']} | {s['rules_always']}/{s['rules_gated']} "
            f"| {s['skills']} ({s['skills_gated']}, {s['skills_user_only']}) | {s['agents']} "
            f"| {s['mcp_tokens']:,} ({', '.join(s['mcp_unmeasured']) or '-'}) "
            f"| {s['long_descriptions']} | {s['leaks']} |"
        )
    out = ["# Start-context exposure", "", "\n".join(rows), ""]
    for r in reports:
        if r.preset != "claude":
            continue
        heavy = sorted((i for i in r.items if i.kind == "inlined-rule"), key=lambda i: -i.bytes)[:8]
        if heavy:
            out.append(f"## {r.repo}: largest always-loaded rules\n")
            out += [f"- `{i.name}` {i.bytes / 1024:.1f} KB" for i in heavy]
            out.append("")
        if r.leaks:
            out.append(f"## {r.repo}: leaked domain terms\n")
            grouped: dict[tuple[str, str], int] = {}
            for leak in r.leaks:
                grouped[(leak.domain, leak.artifact)] = grouped.get((leak.domain, leak.artifact), 0) + leak.count
            for (domain, artifact), count in sorted(grouped.items(), key=lambda kv: -kv[1]):
                out.append(f"- `{domain}` in `{artifact}` ({count} hits)")
            out.append("")
    return "\n".join(out)


def parse_budgets(values: list[str]) -> dict[str, int]:
    """Parse `preset=tokens` budget arguments."""
    budgets = {}
    for value in values:
        preset, _, tokens = value.partition("=")
        if preset not in PRESETS or not tokens.isdigit():
            raise SystemExit(f"--budget expects <preset>=<tokens> with preset in {sorted(PRESETS)}, got {value!r}")
        budgets[preset] = int(tokens)
    return budgets


def gate(reports: list[PresetReport], budgets: dict[str, int], fail_on_leak: bool, fail_on_long: bool) -> list[str]:
    """The reasons a CI run fails: leaks, start tokens over budget, listed descriptions over the limit."""
    failures = []
    for r in reports:
        s = r.summary()
        if fail_on_leak and r.leaks:
            terms = sorted({f"{leak.term} ({leak.artifact})" for leak in r.leaks})
            failures.append(f"{r.repo}/{r.preset}: {len(r.leaks)} leaked term(s): {', '.join(terms)}")
        budget = budgets.get(r.preset)
        if budget is not None and s["start_tokens"] > budget:
            failures.append(f"{r.repo}/{r.preset}: {s['start_tokens']} start tokens, budget {budget}")
        if fail_on_long:
            long = [
                i.name
                for i in r.items
                if i.kind in ("skill", "agent")
                and not i.gated
                and not i.user_only
                and len(i.description) > DESCRIPTION_LIMIT
            ]
            if long:
                failures.append(
                    f"{r.repo}/{r.preset}: descriptions over {DESCRIPTION_LIMIT} characters: {', '.join(long)}"
                )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="+", type=Path)
    parser.add_argument("--domains", type=Path, default=Path(__file__).with_name("domains.toml"))
    parser.add_argument("--presets", default="claude,codex")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--fail-on-leak", action="store_true")
    parser.add_argument("--fail-on-long-descriptions", action="store_true")
    parser.add_argument(
        "--budget",
        action="append",
        default=[],
        metavar="PRESET=TOKENS",
        help="fail when a preset's estimated start tokens exceed TOKENS (repeatable)",
    )
    parser.add_argument(
        "--measure-mcp",
        action="append",
        default=[],
        metavar="SERVER",
        help="start this MCP server (by name, from the preset's config) and count its tool schemas (repeatable)",
    )
    parser.add_argument("--repo-name", help="name to look the repository up by in domains.toml (one repo only)")
    args = parser.parse_args()
    if args.repo_name and len(args.repos) != 1:
        parser.error("--repo-name takes exactly one repository")
    budgets = parse_budgets(args.budget)

    domains = tomllib.loads(args.domains.read_text()) if args.domains.exists() else {}
    if args.fail_on_leak:
        names = [args.repo_name] if args.repo_name else [r.resolve().name for r in args.repos]
        unknown = [n for n in names if n not in domains.get("repos", {})]
        if unknown:
            parser.error(f"--fail-on-leak: {', '.join(unknown)} not listed under [repos] in {args.domains}")
    accept = domains.get("accept", [])
    reports = []
    for repo in args.repos:
        repo = repo.resolve()
        for preset in args.presets.split(","):
            report = PRESETS[preset](repo)
            report.repo = args.repo_name or repo.name
            measure_servers(report, repo, set(args.measure_mcp))
            check_leaks(repo, report, domains, accept)
            reports.append(report)

    text = markdown(reports)
    if args.markdown:
        args.markdown.write_text(text + "\n")
    else:
        print(text)
    if args.json:
        payload = [{"summary": r.summary(), **asdict(r)} for r in reports]
        args.json.write_text(json.dumps(payload, indent=2) + "\n")
    for r in reports:
        s = r.summary()
        print(f"{r.repo}/{r.preset}: {s['start_tokens']} start tokens, {len(r.items)} items, {len(r.leaks)} leaks")
    failures = gate(reports, budgets, args.fail_on_leak, args.fail_on_long_descriptions)
    for failure in failures:
        print(f"::error::{failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

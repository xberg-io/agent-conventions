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
import re
import sys
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
        return sum(i.bytes for i in self.items if not i.gated and not i.user_only)

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


def listing(kind: str, directory: Path, repo: Path, pattern: str) -> list[Item]:
    """A skill or agent costs its name and description at start; the body loads on use."""
    items = []
    for file in sorted(directory.glob(pattern)):
        meta = frontmatter(file.read_text(encoding="utf-8", errors="replace"))
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


def mcp_servers(path: Path) -> list[Item]:
    if not path.exists():
        return []
    try:
        servers = json.loads(path.read_text()).get("mcpServers", {})
    except json.JSONDecodeError:
        return []
    return [Item("mcp", name, str(path.name), len(json.dumps(spec))) for name, spec in servers.items()]


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
    report.items += mcp_servers(repo / ".mcp.json")
    return report


def codex(repo: Path) -> PresetReport:
    report = PresetReport(repo.name, "codex")
    report.items += instructions(repo, ["AGENTS.md"])
    agents_md = repo / "AGENTS.md"
    if agents_md.exists():
        report.items += inlined_rules(read(agents_md))
    report.items += listing("skill", repo / ".agents" / "skills", repo, "*/SKILL.md")
    report.items += listing("agent", repo / ".codex" / "agents", repo, "*.toml")
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
    owner = domains.get("repos", {}).get(repo.name, {}).get("domains", [])
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
                    and re.fullmatch(a.get("repo", ".*"), repo.name)
                    for a in accept
                )
                (report.accepted if accepted else report.leaks).append(leak)


def markdown(reports: list[PresetReport]) -> str:
    rows = [
        (
            "| Repo | Preset | Start tokens | Root file | Inlined rules | Rules always/gated "
            "| Skills (gated, user-only) | Agents | Descr. > 250 | Leaks |"
        ),
        "|---|---|---:|---:|---:|---|---|---:|---:|---:|",
    ]
    for r in reports:
        s = r.summary()
        rows.append(
            f"| {s['repo']} | {s['preset']} | {s['start_tokens']:,} | {s['instruction_bytes'] / 1024:.1f} KB "
            f"| {s['inlined_rules']} | {s['rules_always']}/{s['rules_gated']} "
            f"| {s['skills']} ({s['skills_gated']}, {s['skills_user_only']}) | {s['agents']} "
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="+", type=Path)
    parser.add_argument("--domains", type=Path, default=Path(__file__).with_name("domains.toml"))
    parser.add_argument("--presets", default="claude,codex")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--fail-on-leak", action="store_true")
    args = parser.parse_args()

    domains = tomllib.loads(args.domains.read_text()) if args.domains.exists() else {}
    accept = domains.get("accept", [])
    reports = []
    for repo in args.repos:
        repo = repo.resolve()
        for preset in args.presets.split(","):
            report = PRESETS[preset](repo)
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
    return 1 if args.fail_on_leak and any(r.leaks for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())

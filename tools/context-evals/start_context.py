"""The eval harness's static model of a Claude Code session start, and domains.toml term matching.

Scoring reads it to name what a recorded session loaded and to estimate start tokens when a transcript carries no
usage. It is not a gate: CI gates the start context with ai-rulez's native exposure checks
(actions/context-exposure).
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CALIBRATION = json.loads(Path(__file__).with_name("calibration.json").read_text())
BYTES_PER_TOKEN = float(CALIBRATION["bytes_per_token"])
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
class StartReport:
    items: list[Item] = field(default_factory=list)

    def start_tokens(self) -> int:
        return round(sum(i.bytes for i in self.items if not i.gated and not i.user_only) / BYTES_PER_TOKEN)


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


def claude(repo: Path) -> StartReport:
    """Root instruction files, rules, and skill and agent listings a Claude Code session sees at the root."""
    report = StartReport()
    # Claude Code reads AGENTS.md only through an `@AGENTS.md` import once a CLAUDE.md exists.
    claude_md = repo / "CLAUDE.md"
    names = ["CLAUDE.md"]
    if not claude_md.exists() or "@AGENTS.md" in read(claude_md):
        names.append("AGENTS.md")
    for name in names:
        if (repo / name).exists():
            report.items.append(Item("instructions", name, name, len(read(repo / name).encode())))
    rules = repo / ".claude" / "rules"
    for file in sorted(rules.rglob("*.md")) if rules.exists() else []:
        meta = frontmatter(file.read_text(encoding="utf-8", errors="replace"))
        report.items.append(
            Item("rule", file.stem, str(file.relative_to(repo)), len(read(file).encode()), bool(meta.get("paths")))
        )
    report.items += listing("skill", repo / ".claude" / "skills", repo, "*/SKILL.md")
    report.items += listing("agent", repo / ".claude" / "agents", repo, "*.md")
    return report


def term_pattern(term: str) -> re.Pattern[str]:
    """A domain term bounded by non-word characters: `alpha` does not match inside `alphabet`."""
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def is_accepted(accept: list[dict], term: str, artifact: str, repo: str) -> bool:
    return any(
        a.get("term", term) == term
        and re.fullmatch(a.get("artifact", ".*"), artifact)
        and re.fullmatch(a.get("repo", ".*"), repo)
        for a in accept
    )

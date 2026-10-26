"""Parse Claude Code `--output-format stream-json --verbose` transcripts (issue #3, section 5.2).

One JSON object per line. The parser is tolerant: unknown event types and fields are ignored, missing ones default.
It yields what the session was offered at start (the init event), the tool and skill calls in order, the files
read, the final answer, usage, cost and errors, and reconstructs the loaded-context inventory: which instructions,
rules, files and skills entered the context, at which assistant turn, at roughly what token cost.

Assistant turns are counted by distinct `message.id`: Claude Code emits one `assistant` event per content block,
and the blocks of one model response share an id. Events without an id count as their own turn.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import exposure
import yaml
from records import Loaded, Usage

READ_TOOLS = {"Read": "file_path", "NotebookRead": "notebook_path"}
SEARCH_TOOLS = {"Glob": "path", "Grep": "path", "LS": "path"}
SKILL_KEYS = ("skill", "command", "name")
HARNESS_DIR = "tools/context-evals/"
CLARIFY = re.compile(
    r"\b(which (one|area|part|component|repo|repository|crate|package|module|file|service|of)"
    r"|what do you mean|do you mean|did you mean|could you (clarify|specify|tell|share|point)"
    r"|can you (clarify|specify|tell|share|confirm|point)|please (clarify|specify|confirm)"
    r"|are you (asking|referring|looking)|which .{1,40} (do|did|are) you)\b",
    re.IGNORECASE,
)
OFFER = re.compile(
    r"\b(want me to|would you like me to|shall i|should i|do you want me to|let me know if)\b", re.IGNORECASE
)


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    turn: int
    result_chars: int = 0


@dataclass
class Transcript:
    init: dict = field(default_factory=dict)
    calls: list[ToolCall] = field(default_factory=list)
    answer: str = ""
    usage: Usage = field(default_factory=Usage)
    first_usage: Usage | None = None
    cost_usd: float = 0.0
    turns: int = 0
    assistant_turns: int = 0
    error: str = ""

    @property
    def cwd(self) -> str:
        return str(self.init.get("cwd", ""))

    @property
    def model(self) -> str:
        return str(self.init.get("model", ""))

    @property
    def tools(self) -> list[str]:
        return [str(t) for t in self.init.get("tools", [])]

    @property
    def listed_skills(self) -> list[str]:
        return [_name(s) for s in self.init.get("skills", [])]

    @property
    def listed_agents(self) -> list[str]:
        return [_name(a) for a in self.init.get("agents", [])]

    @property
    def mcp_servers(self) -> list[str]:
        return [_name(s) for s in self.init.get("mcp_servers", [])]

    def skills_used(self) -> list[tuple[str, int]]:
        out = []
        for call in self.calls:
            if call.name == "Skill" and _skill_name(call):
                out.append((_skill_name(call), call.turn))
        return out

    def reads(self) -> list[tuple[str, int, int]]:
        """(path as given, turn, characters returned) for each file read, in order."""
        return [
            (str(call.input[key]), call.turn, call.result_chars)
            for call in self.calls
            if (key := READ_TOOLS.get(call.name)) and call.input.get(key)
        ]

    def touched_paths(self) -> list[str]:
        """Every path a tool looked at: files read plus Glob/Grep/LS search roots."""
        paths = [p for p, _, _ in self.reads()]
        for call in self.calls:
            key = SEARCH_TOOLS.get(call.name)
            if key and call.input.get(key):
                paths.append(str(call.input[key]))
        return paths


def _name(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("name", ""))
    return str(item)


def _usage(data: object) -> Usage:
    if not isinstance(data, dict):
        return Usage()
    return Usage(
        input_tokens=int(data.get("input_tokens") or 0),
        cache_creation_tokens=int(data.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(data.get("cache_read_input_tokens") or 0),
        output_tokens=int(data.get("output_tokens") or 0),
    )


def _content_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(str(c.get("text", ""))) if isinstance(c, dict) else len(str(c)) for c in content)
    return 0


def _events(lines: list[str]) -> list[dict]:
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def parse(text: str) -> Transcript:
    t = Transcript()
    by_id: dict[str, ToolCall] = {}
    seen_messages: set[str] = set()
    last_text = ""
    result_seen = False
    for event in _events(text.splitlines()):
        kind = event.get("type")
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        if kind == "system" and event.get("subtype") == "init" and not t.init:
            t.init = event
        elif kind == "assistant":
            mid = message.get("id")
            if mid is None or mid not in seen_messages:
                t.assistant_turns += 1
                if mid is not None:
                    seen_messages.add(mid)
            if t.first_usage is None and isinstance(message.get("usage"), dict):
                t.first_usage = _usage(message["usage"])
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    last_text = str(block["text"])
                elif block.get("type") == "tool_use":
                    call = ToolCall(
                        str(block.get("id", "")),
                        str(block.get("name", "")),
                        block.get("input") or {},
                        t.assistant_turns,
                    )
                    t.calls.append(call)
                    by_id[call.id] = call
        elif kind == "user":
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    call = by_id.get(str(block.get("tool_use_id", "")))
                    if call is not None:
                        call.result_chars = _content_chars(block.get("content"))
        elif kind == "result":
            result_seen = True
            t.answer = str(event.get("result") or "")
            t.usage = _usage(event.get("usage"))
            t.cost_usd = float(event.get("total_cost_usd") or event.get("cost_usd") or 0.0)
            t.turns = int(event.get("num_turns") or 0)
            subtype = str(event.get("subtype", ""))
            if event.get("is_error") or (subtype and subtype != "success"):
                t.error = subtype or "error"
    if not result_seen:
        t.answer = last_text
        t.error = "no result event"
    return t


def parse_file(path: Path) -> Transcript:
    return parse(path.read_text(encoding="utf-8", errors="replace"))


def asked(answer: str) -> bool:
    """Conservative clarification detector.

    True only when the final paragraph ends with a question mark and contains a clarification cue ("which area",
    "do you mean", "could you clarify", ...), and is not an offer of further work ("want me to", "shall I", ...).
    An answer that delivers a result and closes with "Want me to add tests?" is therefore an answer, not an ask;
    a bare rhetorical question is not counted either. Misses (an ask without a cue) count as answers.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", answer.strip()) if p.strip()]
    if not paragraphs:
        return False
    last = paragraphs[-1].rstrip("*_` ")
    if not last.endswith("?") or OFFER.search(last):
        return False
    return bool(CLARIFY.search(last))


def repo_relative(path: str, cwd: str, root: str) -> str:
    """A tool path relative to the session's checkout root; absolute (normalised) when it lies outside it."""
    p = PurePosixPath(path)
    if not p.is_absolute():
        p = PurePosixPath(cwd) / p
    parts: list[str] = []
    for part in p.parts:
        if part == "..":
            if len(parts) > 1:
                parts.pop()
        elif part != ".":
            parts.append(part)
    norm = PurePosixPath(*parts) if parts else PurePosixPath("/")
    base = PurePosixPath(root)
    if root and (norm == base or base in norm.parents):
        return str(norm.relative_to(base)) or "."
    return str(norm)


def session_root(t: Transcript, case_cwd: str) -> str:
    """The checkout root at run time: the init cwd minus the case's start directory."""
    cwd = PurePosixPath(t.cwd)
    rel = PurePosixPath(case_cwd)
    if case_cwd in ("", ".") or not t.cwd:
        return t.cwd
    if len(cwd.parts) > len(rel.parts) and cwd.parts[-len(rel.parts) :] == rel.parts:
        return str(PurePosixPath(*cwd.parts[: -len(rel.parts)]))
    return t.cwd


def contaminated(t: Transcript, root: str, run_dir: str = "") -> list[str]:
    """Paths the session looked at inside the harness (its cases, results) or the run directory."""
    hits = []
    for raw in t.touched_paths():
        absolute = repo_relative(raw, t.cwd, "")
        rel = repo_relative(raw, t.cwd, root)
        inside_run = bool(run_dir) and (absolute + "/").startswith(run_dir.rstrip("/") + "/")
        if inside_run or (rel + "/").startswith(HARNESS_DIR) or f"/{HARNESS_DIR}" in absolute + "/":
            hits.append(rel)
    return hits


def glob_regex(pattern: str) -> re.Pattern[str]:
    """gitignore-style glob: `**` spans directories, `*` and `?` stay within one, `{a,b}` alternates."""
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif c == "*":
            out, i = out + "[^/]*", i + 1
        elif c == "?":
            out, i = out + "[^/]", i + 1
        elif c == "{" and "}" in pattern[i:]:
            end = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(a) for a in pattern[i + 1 : end].split(",")) + ")"
            i = end + 1
        else:
            out, i = out + re.escape(c), i + 1
    return re.compile(out + r"\Z")


def rule_paths(file: Path) -> list[str]:
    """The `paths:` globs of a rule's front matter (a list or a comma-separated string); empty when unscoped."""
    match = exposure.FRONTMATTER.match(file.read_text(encoding="utf-8", errors="replace"))
    if not match:
        return []
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return []
    paths = meta.get("paths") if isinstance(meta, dict) else None
    if isinstance(paths, str):
        return [p.strip() for p in paths.split(",") if p.strip()]
    return [str(p) for p in paths] if isinstance(paths, list) else []


def _tokens(nbytes: int) -> int:
    return round(nbytes / exposure.BYTES_PER_TOKEN)


def _file_tokens(path: Path) -> int:
    return _tokens(len(exposure.read(path).encode())) if path.is_file() else 0


def _start_items(context: Path, case_cwd: str) -> list[Loaded]:
    report = exposure.claude(context)
    items = [Loaded("instructions", i.path, 0, _tokens(i.bytes)) for i in report.items if i.kind == "instructions"]
    items += [Loaded("rule", i.path, 0, _tokens(i.bytes)) for i in report.items if i.kind == "rule" and not i.gated]
    # Claude Code loads the CLAUDE.md of every directory from the root down to the start directory.
    for directory in list(reversed(PurePosixPath(case_cwd).parents))[1:] + [PurePosixPath(case_cwd)]:
        if str(directory) in ("", "."):
            continue
        nested = context / directory / "CLAUDE.md"
        if nested.is_file():
            items.append(Loaded("instructions", str(directory / "CLAUDE.md"), 0, _file_tokens(nested)))
    return items


def scoped_rules(context: Path) -> list[tuple[str, list[re.Pattern[str]]]]:
    rules_dir = context / ".claude" / "rules"
    out = []
    for file in sorted(rules_dir.rglob("*.md")) if rules_dir.exists() else []:
        globs = rule_paths(file)
        if globs:
            out.append((str(file.relative_to(context)), [glob_regex(g) for g in globs]))
    return out


def skill_file(context: Path, name: str) -> Path | None:
    for base in (context / ".claude" / "skills", context / ".agents" / "skills"):
        for file in sorted(base.glob("*/SKILL.md")) if base.exists() else []:
            if (exposure.metadata(file).get("name") or file.parent.name) == name:
                return file
    return None


def _skill_name(call: ToolCall) -> str:
    return next((str(call.input[k]) for k in SKILL_KEYS if call.input.get(k)), "").lstrip("/")


def _read_triggers(rel: str, turn: int, context: Path, rules: list, present: set[str]) -> list[Loaded]:
    """Scoped rules whose globs match a read file, and CLAUDE.md files in its directory chain, not yet loaded."""
    out = []
    for name, patterns in rules:
        if name not in present and any(p.match(rel) for p in patterns):
            present.add(name)
            out.append(Loaded("rule", name, turn, _file_tokens(context / name)))
    for directory in reversed(PurePosixPath(rel).parents):
        nested = "CLAUDE.md" if str(directory) == "." else str(directory / "CLAUDE.md")
        if nested not in present and (context / nested).is_file():
            present.add(nested)
            out.append(Loaded("instructions", nested, turn, _file_tokens(context / nested)))
    return out


def inventory(t: Transcript, context: Path, case_cwd: str, root: str | None = None) -> list[Loaded]:
    """Reconstruct what entered the context, in order.

    `context` is a directory holding the checkout's context files (the checkout itself, or the snapshot the runner
    keeps in the run directory); `root` is the checkout path at run time, derived from the init cwd when omitted.
    File tokens come from the characters the Read returned, so the files themselves are not needed.
    """
    root = session_root(t, case_cwd) if root is None else root
    items = _start_items(context, case_cwd)
    present = {i.name for i in items}
    rules = scoped_rules(context)
    for call in t.calls:
        key = READ_TOOLS.get(call.name)
        if key and call.input.get(key):
            rel = repo_relative(str(call.input[key]), t.cwd, root)
            items.append(Loaded("file", rel, call.turn, _tokens(call.result_chars)))
            if not PurePosixPath(rel).is_absolute():
                items += _read_triggers(rel, call.turn, context, rules, present)
        elif call.name == "Skill" and _skill_name(call):
            file = skill_file(context, _skill_name(call))
            items.append(Loaded("skill", _skill_name(call), call.turn, _file_tokens(file) if file else 0))
    return items

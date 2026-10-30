"""Prove model-input compatibility across an explicitly reviewed collection transition."""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
from pathlib import Path

from continuation import ContinuationError

SYMBOLS = {
    "gateway.py": ("Policy",),
    "gateway_transport.py": (
        "AnthropicProvider",
        "provider_headers",
        "Backend",
        "InitGate",
        "child_environment",
        "sandbox_command",
        "file_profile",
        "verify_sandbox",
        "validate_writable_home",
        "isolated_process",
        "HardExecute.__init__",
        "HardExecute.profile",
    ),
    "runner.py": (
        "ClaudeAdapter",
        "SessionSpec",
        "RunConfig",
        "Runner.generate",
        "Runner.reset",
        "Runner.prepare_context",
        "snapshot_context",
        "context_fingerprint",
        "binary_fingerprint",
    ),
}
OLD_TAIL = """if result.timed_out or result.returncode or not gate.valid or runner.tool_profile_error(result.stdout, tools):
    self.ledger.stop("CLI execution did not complete with the verified tool profile")
return result"""
NEW_TAIL = "return certify_cli_result(result, argv, gate, tools, self.ledger)"
INHERITED = """inherited = self.inherited.get((case.id, repeat))
if inherited is not None:
    metas.append(inherited)
    continue"""


def symbol_node(tree: ast.AST, name: str) -> ast.AST:
    node = tree
    for part in name.split("."):
        matches = [item for item in getattr(node, "body", []) if getattr(item, "name", None) == part]
        if len(matches) != 1:
            raise ContinuationError("model-behavior proof cannot resolve an exact symbol")
        node = matches[0]
    return node


def ast_hash(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def symbol_hash(source: str, name: str) -> str:
    return ast_hash(symbol_node(ast.parse(source), name))


def execution_prefix(source: str, *, previous: bool) -> ast.AST:
    node = symbol_node(ast.parse(source), "HardExecute.__call__")
    outer = node.body[-1]
    if not isinstance(outer, ast.With) or len(outer.body) < 3 or not isinstance(outer.body[1], ast.With):
        raise ContinuationError("unknown CLI execution structure")
    expected = ast.parse(OLD_TAIL if previous else NEW_TAIL).body
    if [ast.dump(item) for item in outer.body[2:]] != [ast.dump(item) for item in expected]:
        raise ContinuationError("unreviewed CLI classification tail")
    outer.body = outer.body[:2]
    return node


class MetadataOnly(ast.NodeTransformer):
    def visit_Assign(self, node: ast.Assign) -> ast.AST | None:
        expected = ast.parse("meta.bounded_failure = done.bounded_failure\nmeta.collection = done.collection").body
        return None if any(ast.dump(node) == ast.dump(item) for item in expected) else self.generic_visit(node)

    def visit_For(self, node: ast.For) -> ast.AST:
        node = self.generic_visit(node)
        expected = ast.parse(INHERITED).body
        if [ast.dump(item) for item in node.body[:2]] == [ast.dump(item) for item in expected]:
            node.body = node.body[2:]
        return node


def compare_ast(output: dict, label: str, first: ast.AST, second: ast.AST) -> None:
    old, new = ast_hash(first), ast_hash(second)
    if old != new:
        raise ContinuationError(f"model-behavior source changed: {label}")
    output[label] = new


def check_sources(previous: dict[str, str], current: dict[str, str]) -> dict[str, str]:
    output = {}
    for filename, symbols in SYMBOLS.items():
        for name in symbols:
            compare_ast(
                output,
                f"{filename}:{name}",
                symbol_node(ast.parse(previous[filename]), name),
                symbol_node(ast.parse(current[filename]), name),
            )
    compare_ast(
        output,
        "gateway_transport.py:HardExecute.execution-prefix",
        execution_prefix(previous["gateway_transport.py"], previous=True),
        execution_prefix(current["gateway_transport.py"], previous=False),
    )
    for name in ("Runner.session", "Runner.run_worker"):
        compare_ast(
            output,
            f"runner.py:{name}:metadata-only",
            MetadataOnly().visit(symbol_node(ast.parse(previous["runner.py"]), name)),
            MetadataOnly().visit(symbol_node(ast.parse(current["runner.py"]), name)),
        )
    compare_ast(output, "judge.py:module", ast.parse(previous["judge.py"]), ast.parse(current["judge.py"]))
    return output


def git_source(ref: str, filename: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", ref) or filename not in (*SYMBOLS, "judge.py"):
        raise ContinuationError("source proof requires an exact reviewed commit and known controller file")
    result = subprocess.run(
        ["git", "show", f"{ref}:tools/context-evals/{filename}"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        check=False,
    )
    if result.returncode:
        raise ContinuationError("reviewed source object is unavailable")
    return result.stdout


def proof(previous_ref: str, reviewed_ref: str) -> dict:
    previous = {name: git_source(previous_ref, name) for name in (*SYMBOLS, "judge.py")}
    current = {name: git_source(reviewed_ref, name) for name in (*SYMBOLS, "judge.py")}
    return {
        "version": 1,
        "previous_ref": previous_ref,
        "reviewed_ref": reviewed_ref,
        "symbols": check_sources(previous, current),
        "declared_differences": [
            "post-execution task classification",
            "persisted completion metadata",
            "exact inherited trial selection",
        ],
    }


CAPTURE_TAIL = """stdout = output.decode("utf-8", errors="replace")
stderr = errors.decode("utf-8", errors="replace")
result = runner.Completed(130 if interrupted else process.returncode, stdout, stderr, timed_out=timed_out)
if interrupted:
    raise runner.Interrupted(result)
return result"""
PRIOR_CAPTURE_TAIL = """return runner.Completed(process.returncode,
    output.decode("utf-8", errors="replace"), errors.decode("utf-8", errors="replace"), timed_out=timed_out)"""
INTERRUPTED_SESSION = """try:
    done = self.execute(self.adapter.command(spec), cwd, self.adapter.env(Path(home), self.environ), self.config.timeout)
except Interrupted as exc:
    meta.seconds = round(time.monotonic() - started, 3)
    save_interrupted(transcripts, name, meta, exc.completed)
    raise"""
PRIOR_SESSION_CALL = """done = self.execute(self.adapter.command(spec), cwd,
    self.adapter.env(Path(home), self.environ), self.config.timeout)"""


class ExactObservability(ast.NodeTransformer):
    def __init__(self, replacements: list) -> None:
        self.replacements = replacements
        self.counts = [0] * len(replacements)

    def visit(self, node: ast.AST) -> ast.AST | None:
        import copy

        for index, (pattern, replacement) in enumerate(self.replacements):
            if ast.dump(node) == ast.dump(pattern):
                self.counts[index] += 1
                return copy.deepcopy(replacement)
        return super().visit(node)

    def checked(self, node: ast.AST) -> ast.AST:
        result = self.visit(node)
        if result is None or self.counts != [1] * len(self.replacements):
            raise ContinuationError("unknown observability-only source transition")
        return result


def observability_symbol(source: str, name: str) -> ast.AST:
    node = symbol_node(ast.parse(source), name)
    if name == "Backend":
        pattern = ast.parse('if stage == "policy":\n    diagnostic = policy_diagnostic(payload, exc)').body[0]
        return ExactObservability([(pattern, None)]).checked(node)
    if name == "Runner.session":
        return ExactObservability(
            [(ast.parse(INTERRUPTED_SESSION).body[0], ast.parse(PRIOR_SESSION_CALL).body[0])]
        ).checked(node)
    if name != "isolated_process":
        raise ContinuationError("unreviewed observability source exception")
    tail = ast.parse(CAPTURE_TAIL).body
    if [ast.dump(item) for item in node.body[-len(tail) :]] != [ast.dump(item) for item in tail]:
        raise ContinuationError("unknown interrupted capture tail")
    node.body[-len(tail) :] = ast.parse(PRIOR_CAPTURE_TAIL).body
    deadline = ast.parse("deadline, timed_out, interrupted = time.monotonic() + timeout, False, False").body[0]
    previous = ast.parse("deadline, timed_out = time.monotonic() + timeout, False").body[0]
    handler = ast.parse("try:\n    pass\nexcept KeyboardInterrupt:\n    interrupted = True").body[0].handlers[0]
    return ExactObservability([(deadline, previous), (handler, None)]).checked(node)


def extension_check_sources(previous: dict[str, str], current: dict[str, str]) -> dict:
    output = {}
    for filename, symbols in SYMBOLS.items():
        for name in symbols:
            if name not in ("Backend", "isolated_process"):
                compare_ast(
                    output,
                    f"{filename}:{name}",
                    symbol_node(ast.parse(previous[filename]), name),
                    symbol_node(ast.parse(current[filename]), name),
                )
    for filename, name, label in (
        ("gateway_transport.py", "Backend", "observability-only"),
        ("gateway_transport.py", "isolated_process", "observability-only"),
        ("runner.py", "Runner.session", "interruption-only"),
    ):
        compare_ast(
            output,
            f"{filename}:{name}:{label}",
            symbol_node(ast.parse(previous[filename]), name),
            observability_symbol(current[filename], name),
        )
    for filename, names in {
        "gateway.py": ("rates", "Ledger", "StreamUsage"),
        "gateway_transport.py": (
            "HardExecute.__call__",
            "maximum_turn_failure",
            "certify_cli_result",
            "terminal_event",
        ),
        "runner.py": ("Runner.run_worker",),
    }.items():
        for name in names:
            compare_ast(
                output,
                f"{filename}:{name}",
                symbol_node(ast.parse(previous[filename]), name),
                symbol_node(ast.parse(current[filename]), name),
            )
    compare_ast(output, "judge.py:module", ast.parse(previous["judge.py"]), ast.parse(current["judge.py"]))
    return output


def extension_proof(previous_ref: str, reviewed_ref: str) -> dict:
    previous = {name: git_source(previous_ref, name) for name in (*SYMBOLS, "judge.py")}
    current = {name: git_source(reviewed_ref, name) for name in (*SYMBOLS, "judge.py")}
    return {
        "version": 2,
        "previous_ref": previous_ref,
        "reviewed_ref": reviewed_ref,
        "declared_differences": ["redacted-policy-diagnostics", "interrupted-evidence-preservation"],
        "symbols": extension_check_sources(previous, current),
    }

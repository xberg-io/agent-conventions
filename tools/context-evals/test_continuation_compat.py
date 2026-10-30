"""Compatibility proofs reject model-visible source drift, not merely version labels."""

import ast
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import continuation
import continuation_compat

OLD_TAIL = """if result.timed_out or result.returncode or not gate.valid or runner.tool_profile_error(result.stdout, tools):
    self.ledger.stop("CLI execution did not complete with the verified tool profile")
return result"""


class PreviousMetadata(ast.NodeTransformer):
    def visit_Assign(self, node):
        if ast.unparse(node).startswith(("meta.bounded_failure =", "meta.collection =")):
            return None
        return self.generic_visit(node)

    def visit_Return(self, node):
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "certify_cli_result"
        ):
            return ast.parse(OLD_TAIL).body
        return self.generic_visit(node)


def sources() -> tuple[dict, dict]:
    current = {
        name: (Path(__file__).parent / name).read_text()
        for name in ("gateway.py", "gateway_transport.py", "runner.py", "judge.py")
    }
    previous = {name: ast.unparse(PreviousMetadata().visit(ast.parse(value))) for name, value in current.items()}
    return previous, current


class CompatibilityProofTest(unittest.TestCase):
    def test_declared_post_execution_classification_and_metadata_do_not_change_model_inputs(self) -> None:
        previous, current = sources()
        proof = continuation_compat.check_sources(previous, current)
        self.assertGreater(len(proof), 15)
        self.assertEqual(proof["gateway.py:Policy"], continuation_compat.symbol_hash(current["gateway.py"], "Policy"))

    def test_changed_provider_header_sandbox_and_command_are_rejected(self) -> None:
        previous, current = sources()
        targets = [
            ("gateway_transport.py", "provider_headers"),
            ("gateway_transport.py", "sandbox_command"),
            ("runner.py", "ClaudeAdapter.command"),
            ("gateway.py", "Policy.prepare"),
        ]
        for filename, symbol in targets:
            changed = copy.deepcopy(current)
            tree = ast.parse(changed[filename])
            target = continuation_compat.symbol_node(tree, symbol)
            target.body.insert(0, ast.parse("unexpected_model_visible_change()").body[0])
            changed[filename] = ast.unparse(tree)
            with self.subTest(symbol=symbol), self.assertRaises(continuation.ContinuationError):
                continuation_compat.check_sources(previous, changed)

    def test_arbitrary_execution_prefix_change_cannot_hide_in_the_declared_tail_exception(self) -> None:
        previous, current = sources()
        tree = ast.parse(current["gateway_transport.py"])
        node = continuation_compat.symbol_node(tree, "HardExecute.__call__")
        node.body.insert(0, ast.parse("unexpected_before_model()").body[0])
        current["gateway_transport.py"] = ast.unparse(tree)
        with self.assertRaises(continuation.ContinuationError):
            continuation_compat.check_sources(previous, current)


if __name__ == "__main__":
    unittest.main()


class PreviousObservability(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if node.name == "isolated_process":
            node.body[-5:] = ast.parse("""return runner.Completed(process.returncode,
                output.decode("utf-8", errors="replace"), errors.decode("utf-8", errors="replace"), timed_out=timed_out)""").body
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if ast.unparse(node).startswith("deadline, timed_out, interrupted ="):
            node.targets[0].elts.pop()
            node.value.elts.pop()
        return self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        return None if ast.unparse(node.type) == "KeyboardInterrupt" else self.generic_visit(node)

    def visit_If(self, node):
        return None if ast.unparse(node.test) == "stage == 'policy'" else self.generic_visit(node)

    def visit_Try(self, node):
        if any(isinstance(item.type, ast.Name) and item.type.id == "Interrupted" for item in node.handlers):
            return node.body
        return self.generic_visit(node)


class ExtensionCompatibilityTest(unittest.TestCase):
    def fixtures(self):
        current = {
            name: (Path(__file__).parent / name).read_text()
            for name in ("gateway.py", "gateway_transport.py", "runner.py", "judge.py")
        }
        previous = {
            name: ast.unparse(PreviousObservability().visit(ast.parse(value))) for name, value in current.items()
        }
        return previous, current

    def test_exact_reviewed_observability_exceptions_preserve_normal_model_execution(self) -> None:
        previous, current = self.fixtures()
        proof = continuation_compat.extension_check_sources(previous, current)
        self.assertGreater(len(proof), 20)
        self.assertIn("gateway_transport.py:isolated_process:observability-only", proof)
        self.assertIn("runner.py:Runner.session:interruption-only", proof)

    def test_unreviewed_exception_provider_or_command_changes_are_rejected(self) -> None:
        for filename, symbol in [
            ("gateway_transport.py", "Backend.respond"),
            ("gateway_transport.py", "isolated_process"),
            ("runner.py", "Runner.session"),
            ("runner.py", "ClaudeAdapter.command"),
        ]:
            previous, current = self.fixtures()
            tree = ast.parse(current[filename])
            continuation_compat.symbol_node(tree, symbol).body.insert(0, ast.parse("unreviewed_change()").body[0])
            current[filename] = ast.unparse(tree)
            with self.subTest(symbol=symbol), self.assertRaises(continuation.ContinuationError):
                continuation_compat.extension_check_sources(previous, current)

    def test_declared_observability_handlers_cannot_hide_extra_behavior(self) -> None:
        for filename, symbol in (
            ("gateway_transport.py", "Backend.respond"),
            ("gateway_transport.py", "isolated_process"),
            ("runner.py", "Runner.session"),
        ):
            previous, current = self.fixtures()
            tree = ast.parse(current[filename])
            function = continuation_compat.symbol_node(tree, symbol)
            if symbol == "Backend.respond":
                target = next(
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.If) and ast.unparse(node.test) == "stage == 'policy'"
                )
            else:
                target = next(
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.ExceptHandler)
                    and isinstance(node.type, ast.Name)
                    and node.type.id in ("KeyboardInterrupt", "Interrupted")
                )
            target.body.insert(0, ast.parse("unreviewed_exception_side_effect()").body[0])
            current[filename] = ast.unparse(tree)
            with self.subTest(symbol=symbol), self.assertRaises(continuation.ContinuationError):
                continuation_compat.extension_check_sources(previous, current)

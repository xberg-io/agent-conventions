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

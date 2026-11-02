"""Exercise actual handler AST without importing app startup / live services."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


class PrefetchRouteTests(unittest.TestCase):
    def test_only_explicit_prefetch_flag_selects_early_route(self):
        source = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8-sig"))
        node = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "control_replenish_task")
        node.decorator_list = []
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        receiver = Mock(return_value={"ok": True})
        namespace = {"require_control_permission": Mock(), "receiver_json": receiver}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "actual-control-route", "exec"), namespace)
        for flag, expected in ((True, "prefetch-replenish"), (False, "replenish"), ("true", "replenish")):
            class Request:
                async def json(self):
                    return {"prefetch": flag, "urls": "fixture"}
            coroutine = namespace["control_replenish_task"]("task-6", Request())
            try:
                coroutine.send(None)
            except StopIteration:
                pass
            else:
                coroutine.close()
                self.fail("Fixture unexpectedly requested external asynchronous I/O")
            self.assertEqual(f"/api/tasks/{expected}/task-6", receiver.call_args.args[0])
        self.assertEqual(3, namespace["require_control_permission"].call_count)

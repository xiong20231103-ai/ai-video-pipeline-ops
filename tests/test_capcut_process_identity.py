"""CapCut is detected by process name, never by another command line."""
import ast
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path, function):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == function)
    node.returns = None
    for argument in node.args.args:
        argument.annotation = None
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class FakeProcess:
    def __init__(self, pid, name, cmdline):
        self.info = {"pid": pid, "name": name, "cmdline": cmdline}


def fake_psutil(processes):
    return types.SimpleNamespace(process_iter=lambda fields: iter(processes),
                                 AccessDenied=PermissionError, NoSuchProcess=LookupError)


EXECUTOR = FakeProcess(1, "python.exe", [
    r"E:\wb\.venv\Scripts\python.exe", r"E:\wb\capcut_executor_host.py", "--root", r"E:\pip",
    "--client", r"E:\client\bin\CapCutBatchClient.exe", "--resident"])
CLIENT = FakeProcess(2, "CapCutBatchClient.exe", [r"E:\client\bin\CapCutBatchClient.exe", "--handoff", "m.json"])


class Tests(unittest.TestCase):
    def check_process_status(self, path):
        namespace = load(path, "process_status")
        namespace["psutil"] = fake_psutil([EXECUTOR])
        self.assertFalse(namespace["process_status"]()["capcut"], path)
        namespace["psutil"] = fake_psutil([EXECUTOR, CLIENT])
        self.assertTrue(namespace["process_status"]()["capcut"], path)

    def test_dashboard_ignores_resident_pip_executor(self):
        self.check_process_status(ROOT / "app.py")

    def test_agent_ignores_resident_pip_executor(self):
        self.check_process_status(ROOT / "agent" / "core" / "compatibility_logic.py")

    def test_draft_cleanup_ignores_resident_pip_executor(self):
        namespace = load(ROOT / "app.py", "_capcut_draft_processes")
        namespace["Any"] = object
        namespace["psutil"] = fake_psutil([EXECUTOR])
        self.assertEqual(namespace["_capcut_draft_processes"](), [])
        namespace["psutil"] = fake_psutil([EXECUTOR, CLIENT, FakeProcess(3, "CapCut.exe", [])])
        self.assertEqual([row["pid"] for row in namespace["_capcut_draft_processes"]()], [2, 3])


if __name__ == "__main__":
    unittest.main()

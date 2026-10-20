"""Run the test suite from its worktree with production I/O blocked."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / ".test-deps"))
assert Path.cwd().resolve() == root
sys.path.insert(0, str(root))
sys.dont_write_bytecode = True

with tempfile.TemporaryDirectory(prefix="ops-isolated-") as scratch:
    isolated = Path(scratch)
    os.environ["LOCALAPPDATA"] = str(isolated / "localappdata")
    config = {
        key: str(isolated / key)
        for key in (
            "workbench_dir", "workbench_ops_status", "download_state_file",
            "download_project_status_file", "download_root", "voice_handoff_file",
            "generation_output_root", "capcut_handoff_dir", "fourth_step_handoff_dir",
            "final_output_root", "capcut_draft_root", "upload_status_file",
        )
    }
    config.update(simulation_enabled=False, audio_roots=[], prepared_sample_roots=[],
                  capcut_test_roots=[], baidu_sync_roots=[], receiver_status_url="",
                  control_plane_url="http://127.0.0.1:18790")
    original_read_text = Path.read_text
    def read_text(path, *args, **kwargs):
        if path.resolve() == root / "config.json":
            return json.dumps(config)
        return original_read_text(path, *args, **kwargs)

    # Prevent unexpected writes to any production location, even from a test.
    write_roots = (root, isolated.resolve(), Path(tempfile.gettempdir()).resolve())
    def permitted(path):
        if isinstance(path, int):
            return True
        try:
            if isinstance(path, str) and path.startswith('file:'):
                from urllib.parse import urlsplit, unquote
                parsed = urlsplit(path)
                if parsed.netloc not in {'', 'localhost'}:
                    return False
                path = unquote(parsed.path)
                if os.name == 'nt' and len(path) > 3 and path[0] == '/' and path[2] == ':':
                    path = path[1:]
            resolved = Path(path).resolve()
            return any(resolved.is_relative_to(base) for base in write_roots)
        except (ValueError, TypeError):
            return False
    def audit(event, args):
        paths = ()
        if event == "open":
            path, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or (flags and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                paths = (path,)
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime"}:
            paths = args[:1]
        elif event in {"os.rename", "os.link", "os.symlink"}:
            paths = args[:2]
        elif event == "sqlite3.connect" and str(args[0]) != ":memory:":
            paths = args[:1]
        elif event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system"}:
            # Windows asyncio implements its internal socketpair with ephemeral
            # loopback TCP. Permit ONLY that exact stdlib frame, never arbitrary
            # localhost/service connections or application listeners.
            frame = sys._getframe()
            pair_codes = {getattr(getattr(socket, name, None), "__code__", None) for name in ("_fallback_socketpair", "socketpair")} - {None}
            internal_pair = False
            while frame:
                if frame.f_code in pair_codes:
                    internal_pair = True
                    break
                frame = frame.f_back
            address = args[1] if event in {"socket.connect", "socket.bind"} else None
            if not (internal_pair and isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and (event != "socket.bind" or address[1] == 0)):
                raise RuntimeError("Production network/process execution blocked: " + event)
        if any(not permitted(path) for path in paths):
            raise RuntimeError("Write outside worktree/temp blocked: " + event)
    sys.addaudithook(audit)
    with patch.object(Path, "read_text", read_text):
        import app
    assert app.BASE_DIR == root
    if os.environ.get("OPS_WRITE_GOLDEN") == "fixture-receiver-only":
        from contracts.golden import replay_receiver
        fixtures = json.loads((root / "tests/fixtures/golden/receiver-inputs.json").read_text(encoding="utf-8"))
        expected = {name: replay_receiver(app, fixture) for name, fixture in fixtures.items()}
        (root / "tests/fixtures/golden/receiver-expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Generated frozen receiver adapter fixtures only; no live inputs.")
    with patch("app.urllib.request.urlopen", side_effect=RuntimeError("Live HTTP blocked")), \
         patch.object(subprocess, "Popen", side_effect=RuntimeError("Process launch blocked")):
        suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    print("Isolation: worktree/temp writes only; live HTTP and process launches blocked.")
    sys.exit(0 if result.wasSuccessful() else 1)

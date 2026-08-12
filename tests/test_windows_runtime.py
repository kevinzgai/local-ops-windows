import os
import shutil
import sys
import tempfile
import time
import unittest

import server
from server import Config

WIN = sys.platform == "win32"


@unittest.skipUnless(WIN, "仅 Windows")
class RuntimeTests(unittest.TestCase):
    def test_data_dir_under_appdata(self):
        self.assertIn("总控台", server.DEFAULT_DATA_DIR)
        self.assertTrue(server.DATA_DIR)

    def test_instance_lock_single_and_release(self):
        path = os.path.join(
            os.environ.get("TEMP", "."), "console-lock-win-test.lock")
        if os.path.exists(path):
            os.remove(path)
        f1 = server.acquire_instance_lock(path)
        f2 = server.acquire_instance_lock(path)
        self.assertIsNotNone(f1)
        self.assertIsNone(f2)
        server.release_instance_lock(f1)


@unittest.skipUnless(WIN, "仅 Windows")
class SpawnStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="console-e2e-")
        self.cfg = Config(os.path.join(self.tmp, "config.json"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spawn_tree_stop(self):
        app = {"id": "aabbccdd", "name": "srv",
               "command": '"%s" -m http.server 8123' % sys.executable,
               "cwd": self.tmp, "port": 8123, "kind": "service"}
        def op(c):
            c["apps"].append(app)
            return True
        self.cfg.update(op)
        ok, err, proc, anchor, token = server.start_app(app)
        self.assertTrue(ok, err)
        server.persist_started_app(self.cfg, app["id"], proc, anchor, token)
        tracked = server.find_app(self.cfg.snapshot(), app["id"])
        deadline = time.time() + 10
        while time.time() < deadline:
            if server.managed_pids(tracked):
                break
            time.sleep(0.2)
        self.assertTrue(server.managed_pids(tracked))
        ok, err = server.stop_app_and_clear(self.cfg, tracked, timeout=10)
        self.assertTrue(ok, err)
        self.assertFalse(server.managed_pids(tracked))

    def test_task_exit_code_recorded(self):
        app = {"id": "11223344", "name": "task",
               "command": '"%s" -c "import sys; sys.exit(3)"' % sys.executable,
               "cwd": self.tmp, "port": None, "kind": "task"}
        ok, err, proc, anchor, token = server.start_app(app)
        self.assertTrue(ok, err)
        done = proc.wait(timeout=15)
        self.assertEqual(done, 3)


@unittest.skipUnless(WIN, "仅 Windows")
class ClassifyTests(unittest.TestCase):
    def test_system_path_is_background(self):
        self.assertEqual(server.classify_group(
            "foo:1", "foo", r"c:\windows\system32\foo.exe",
            r"c:\windows\system32\foo.exe --x", None, set()), "background")

    def test_dev_keyword_is_mine(self):
        self.assertEqual(server.classify_group(
            "n:9", "python.exe", "python.exe", "python app.py",
            "C:\\a", set()), "mine")

    def test_origin_self_console(self):
        table = {1: (0, ""), server.SELF_PID: (1, "python server.py"),
                 41: (server.SELF_PID, "cmd.exe")}
        self.assertEqual(server.attribute_origin(41, table),
                         {"label": "总控台", "icon": "rocket"})

    def test_origin_code_exe_alias(self):
        # Parent process is Code.exe; child pid=99 has ppid=77 (Code.exe).
        # Without _ORIGIN_APP_ALIASES wiring, child would fall through to
        # the generic basename candidate ("Code.exe", icon "package").
        # Note: attribute_origin uses parent_args.split()[0] which breaks
        # on paths with spaces; using a no-space path here exercises the
        # alias lookup, not the quote-splitting heuristic.
        table = {1: (0, ""), 77: (1, r"C:\Code\Code.exe"),
                 99: (77, "node server.js")}
        self.assertEqual(server.attribute_origin(99, table),
                         {"label": "VS Code", "icon": "code"})


@unittest.skipUnless(WIN, "仅 Windows")
class PickAndCommandTests(unittest.TestCase):
    def test_command_for_py(self):
        self.assertEqual(server.command_for_script(r"C:\a\b.py").split()[0], "python")
        self.assertIn("b.py", server.command_for_script(r"C:\a\b.py"))

    def test_command_for_ps1(self):
        self.assertEqual(server.command_for_script(r"C:\a\b.ps1").split()[0], "powershell")

    def test_command_for_bat(self):
        out = server.command_for_script(r"C:\a\b.bat")
        self.assertTrue(out.startswith("call "))
        self.assertIn("b.bat", out)

    def test_quote_cmd_roundtrip(self):
        import platform_win
        self.assertEqual(platform_win.quote_cmd("a b c"), '"a b c"')


@unittest.skipUnless(WIN, "仅 Windows")
class DetectTests(unittest.TestCase):
    def test_static_site_hint(self):
        d = tempfile.mkdtemp(prefix="det-")
        try:
            open(os.path.join(d, "index.html"), "w").write("<html></html>")
            result, err = server.detect_project(d)
            self.assertIsNone(err)
            cmds = [c["command"] for c in result["candidates"]]
            self.assertIn("python -m http.server 8000", cmds)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
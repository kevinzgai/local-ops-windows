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


if __name__ == "__main__":
    unittest.main()
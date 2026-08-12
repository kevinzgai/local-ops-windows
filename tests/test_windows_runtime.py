import os
import sys
import unittest

import server

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


if __name__ == "__main__":
    unittest.main()
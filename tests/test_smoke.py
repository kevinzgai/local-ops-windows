"""控制台端到端冒烟测试（Windows 专用）。

启一个真实的 ThreadingHTTPServer 实例，校验 `/api/health` 与 `/api/state`
至少能返回 200 并包含必要字段。完整 `/api/state` 结构由
`tests.test_server` 的 `StateTests` 与 `managed_process_index` 测试覆盖，
此处只做最薄层的「启停 + HTTP 契约」回归。
"""

import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


IS_WINDOWS = sys.platform == "win32"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipIf(not IS_WINDOWS, "Windows-specific smoke")
class ConsoleSmokeTests(unittest.TestCase):
    def setUp(self):
        from server import ConsoleServer, Handler, Config
        self.port = _free_port()
        cfg_dir = tempfile.mkdtemp(prefix="console-smoke-")
        self.cfg = Config(os.path.join(cfg_dir, "config.json"))
        self.httpd = ConsoleServer(
            ("127.0.0.1", self.port), Handler, self.cfg, self.port)
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.thread.join(timeout=2)
        finally:
            self.httpd = None
            self.thread = None

    def _wait_for(self, path, expect_keys):
        deadline = time.time() + 4.0
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}{path}", timeout=2) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    for key in expect_keys:
                        self.assertIn(key, body)
                    return body
            except (urllib.error.URLError, ConnectionError) as exc:
                last_err = exc
                time.sleep(0.1)
        self.fail(f"server did not respond on {path}: {last_err}")

    def test_health_endpoint(self):
        body = self._wait_for(
            "/api/health", ("version", "schemaVersion"))
        self.assertIn("status", body)
        self.assertIn("degraded", body)

    def test_state_endpoint(self):
        body = self._wait_for(
            "/api/state", ("version", "schemaVersion", "services",
                           "apps", "consolePort"))
        self.assertEqual(body["consolePort"], self.port)


if __name__ == "__main__":
    unittest.main()

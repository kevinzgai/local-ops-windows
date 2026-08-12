import unittest
from unittest import mock

import platform_win as pw

SELF_U = "admin"


class FakeProc:
    def __init__(self, d):
        self._d = d

    @property
    def info(self):
        return dict(self._d)


class PsSnapshotTests(unittest.TestCase):
    def test_returns_expected_fields(self):
        t0 = 1000.0
        fake = FakeProc({
            "pid": 42, "name": "node.exe",
            "cmdline": ["node", "server.js"],
            "create_time": t0 - 60, "memory_percent": 2.5,
            "cpu_percent": 3.2, "username": SELF_U,
        })
        with mock.patch("platform_win.psutil.process_iter",
                        return_value=[fake]), \
             mock.patch("platform_win.time.time", return_value=t0):
            snap = pw.ps_snapshot()
        self.assertEqual(snap[42]["uid"], SELF_U)
        self.assertEqual(snap[42]["comm"], "node.exe")
        self.assertEqual(snap[42]["args"], "node server.js")
        self.assertEqual(snap[42]["etime"], 60)
        self.assertEqual(snap[42]["mem"], 2.5)

    def test_filters_by_pids(self):
        fake = FakeProc({"pid": 7, "name": "a.exe",
                         "cmdline": [], "create_time": 0.0,
                         "memory_percent": 0.0, "cpu_percent": 0.0,
                         "username": SELF_U})
        with mock.patch("platform_win.psutil.process_iter",
                        return_value=[fake]):
            self.assertNotIn(7, pw.ps_snapshot(pids={99}))

    def test_ignores_dead_procs(self):
        fake = FakeProc({"pid": 7, "name": "a.exe", "cmdline": [],
                         "create_time": 0.0, "memory_percent": 0.0,
                         "cpu_percent": 0.0, "username": SELF_U})
        err = mock.Mock()
        type(err).info = mock.PropertyMock(side_effect=psutil_access_denied())
        with mock.patch("platform_win.psutil.process_iter",
                        return_value=[fake, err]):
            snap = pw.ps_snapshot()
        self.assertEqual(set(snap), {7})


class ScanListenerTests(unittest.TestCase):
    def test_builds_pid_port_map(self):
        import socket
        fake_conn = mock.Mock()
        fake_conn.status = "LISTEN"
        fake_conn.laddr = mock.Mock(ip="127.0.0.1", port=8080)
        fake_conn.pid = 12
        conn2 = mock.Mock()
        conn2.status = "LISTEN"
        conn2.laddr = mock.Mock(ip="::1", port=8080)
        conn2.pid = 12
        conn3 = mock.Mock()
        conn3.status = "ESTABLISHED"
        conn3.laddr = mock.Mock(ip="127.0.0.1", port=9999)
        conn3.pid = 12
        with mock.patch("platform_win.psutil.net_connections",
                        return_value=[fake_conn, conn2, conn3]):
            found = pw.scan_listeners()
        self.assertEqual(found[(12, 8080)], {"127.0.0.1", "::1"})
        self.assertNotIn((12, 9999), found)


class CwdTests(unittest.TestCase):
    def test_cwd_returns_path(self):
        proc = mock.Mock()
        proc.cwd.return_value = "C:\\proj"
        with mock.patch("platform_win.psutil.Process",
                        return_value=proc):
            self.assertEqual(pw.lsof_cwds({1}), {1: "C:\\proj"})

    def test_access_denied_skipped(self):
        proc = mock.Mock()
        proc.cwd.side_effect = psutil_denied()
        with mock.patch("platform_win.psutil.Process",
                        return_value=proc):
            self.assertEqual(pw.lsof_cwds({1}), {})


class PidAliveTests(unittest.TestCase):
    def test_alive(self):
        with mock.patch("platform_win.psutil.pid_exists",
                        return_value=True):
            self.assertTrue(pw.pid_alive(42))

    def test_bad_type(self):
        self.assertFalse(pw.pid_alive("abc"))


def psutil_access_denied():
    import psutil
    return psutil.AccessDenied()


def psutil_denied():
    import psutil
    return psutil.AccessDenied()


if __name__ == "__main__":
    unittest.main()
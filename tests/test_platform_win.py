import unittest
from unittest import mock

import platform_win
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


class ProcessTreeTests(unittest.TestCase):
    def test_tree_includes_descendants(self):
        parent = mock.Mock()
        child2 = mock.Mock(pid=5)
        parent.pid = 1
        parent.children.return_value = [child2]
        with mock.patch("platform_win.psutil.Process",
                        return_value=parent):
            self.assertEqual(pw.process_tree(1), [1, 5])

    def test_tree_empty_when_missing(self):
        with mock.patch("platform_win.psutil.Process",
                        side_effect=psutil_no_such_proc()):
            self.assertEqual(pw.process_tree(999), [])

    def test_quote_cmd(self):
        self.assertEqual(pw.quote_cmd(r"C:\proj 文件\app.py"),
                         '"C:\\proj 文件\\app.py"')

    def test_kill_tree_ok(self):
        r = mock.Mock(returncode=0)
        with mock.patch("platform_win.subprocess.run",
                        return_value=r) as m:
            ok, err = pw.kill_tree(99)
        self.assertIsNone(err)
        self.assertTrue(ok)
        self.assertIn("taskkill", str(m.call_args))

    def test_terminate_job_returns_true_and_closes_handle(self):
        with mock.patch("platform_win._ker.TerminateJobObject",
                        return_value=1) as terminate, \
             mock.patch("platform_win._ker.CloseHandle",
                        return_value=1) as close:
            self.assertTrue(pw.terminate_job(0xDEAD))
        terminate.assert_called_once_with(0xDEAD, 1)
        close.assert_called_once_with(0xDEAD)

    def test_terminate_job_closes_even_when_terminate_fails(self):
        with mock.patch("platform_win._ker.TerminateJobObject",
                        return_value=0), \
             mock.patch("platform_win._ker.CloseHandle",
                        return_value=1) as close:
            self.assertFalse(pw.terminate_job(0xBEEF))
        close.assert_called_once_with(0xBEEF)

    def test_terminate_job_handles_none_handle(self):
        with mock.patch("platform_win._ker.CloseHandle") as close:
            self.assertFalse(pw.terminate_job(None))
        close.assert_not_called()

    def test_take_job_returns_none_after_remove(self):
        pw.register_job("once-app", 0xCAFE)
        first = pw.take_job("once-app")
        self.assertEqual(first, 0xCAFE)
        self.assertIsNone(pw.take_job("once-app"))


def psutil_no_such_proc():
    import psutil
    return psutil.NoSuchProcess(999)


class TrayHelpersTests(unittest.TestCase):
    def test_tray_menu_has_expected_items(self):
        self.assertEqual(
            [item[1] for item in platform_win.TRAY_MENU],
            ["打开面板", "停止", "退出"])

    def test_open_panel_url(self):
        self.assertEqual(
            platform_win.open_panel_url("127.0.0.1", 9600),
            "http://127.0.0.1:9600/")

    @mock.patch("platform_win._user32", create=True)
    def test_message_box_calls_user32(self, user32):
        user32.MessageBoxW.return_value = 1
        self.assertTrue(platform_win.message_box("总控台", "错误"))
        user32.MessageBoxW.assert_called_once_with(None, "错误", "总控台", 0x10)


class TrayIconTests(unittest.TestCase):
    def test_dispatch_routes_to_callback(self):
        calls = []
        icon = platform_win.TrayIcon("127.0.0.1", 9600, {
            "open_panel": lambda: calls.append("open"),
            "stop": lambda: calls.append("stop"),
            "quit": lambda: calls.append("quit"),
        })
        icon._dispatch(1)
        icon._dispatch(2)
        icon._dispatch(3)
        self.assertEqual(calls, ["open", "stop", "quit"])

    def test_dispatch_unknown_id_is_noop(self):
        icon = platform_win.TrayIcon("127.0.0.1", 9600, {})
        icon._dispatch(999)  # 不应抛异常

    @mock.patch("platform_win.TrayIcon")
    def test_start_tray_constructs_and_starts(self, cls):
        cb = {"stop": lambda: None}
        result = platform_win.start_tray("127.0.0.1", 9600, cb)
        args, kwargs = cls.call_args
        self.assertEqual(args[0], "127.0.0.1")
        self.assertEqual(args[1], 9600)
        self.assertIs(args[2], cb)
        self.assertIs(result, cls.return_value)
        cls.return_value.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
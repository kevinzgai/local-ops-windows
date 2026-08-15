#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总控台 Windows 平台适配层（psutil 数据面）。

函数签名与 macOS 版一一对应，供 server.py 保持 HTTP/配置层不变。
psutil 是本移植唯一第三方依赖。
"""

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

import psutil

LOG = logging.getLogger("console")

try:
    # psutil 7.x 的 Process.ppid() 每次调用都会重建整张 Toolhelp ppid 表，
    # 逐进程访问会让 process_iter(attrs=["ppid"]) 冷启动慢到 2.5s 以上。
    # 这里直接取一次 C 层的 ppid_map（全量快照，约几毫秒）供批量使用。
    from psutil._pswindows import ppid_map as _ppid_map
except Exception:  # pragma: no cover - 私有 API 跨版本变动时回退逐进程查询
    _ppid_map = None


def current_username():
    """当前登录用户（进程归属比较用）。"""
    try:
        return psutil.Process(os.getpid()).username() or os.getlogin()
    except (psutil.Error, OSError):
        return os.environ.get("USERNAME") or os.getlogin()


def same_user(pid):
    try:
        return process_uid(pid) == current_username()
    except (OSError, ValueError):
        return False


def ps_snapshot(pids=None, with_uid=True):
    """→ {pid: {"uid","comm","args","cpu","mem","etime"}}（uid 为用户名 str）。"""
    want = set(pids) if pids is not None else None
    result = {}
    now = time.time()
    for proc in psutil.process_iter(
            attrs=["pid", "name", "cmdline", "create_time",
                   "memory_percent", "cpu_percent", "username"]):
        try:
            info = proc.info
        except (psutil.Error, AttributeError):
            continue
        pid = info.get("pid")
        if pid is None:
            continue
        if want is not None and pid not in want:
            continue
        name = info.get("name") or ""
        cl = info.get("cmdline")
        args = " ".join(cl) if isinstance(cl, list) else name
        created = info.get("create_time")
        etime = int(max(0.0, now - created)) if isinstance(created, (int, float)) else 0
        cpu = info.get("cpu_percent")
        mem = info.get("memory_percent")
        result[pid] = {
            "uid": info.get("username") if with_uid else None,
            "comm": name,
            "args": args,
            "cpu": round(float(cpu) if cpu is not None else 0.0, 2),
            "mem": round(float(mem) if mem is not None else 0.0, 2),
            "etime": etime,
        }
    return result


def scan_listeners():
    """psutil 监听快照 → {(pid, port): {bind_host, ...}}。同 mac 的 lsof 版。"""
    found = {}
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status != "LISTEN" or not conn.laddr:
            continue
        pid = conn.pid
        if pid is None:
            continue
        port = conn.laddr.port
        host = conn.laddr.ip or ""
        if host and host.startswith("["):
            host = host.strip("[]")
        found.setdefault((pid, port), set()).add(host or "*")
    return found


def lsof_cwds(pids):
    """→ {pid: cwd}；受限进程（AccessDenied）静默跳过。"""
    result = {}
    for pid in {int(p) for p in pids}:
        try:
            result[pid] = psutil.Process(pid).cwd()
        except (psutil.Error, OSError, ValueError):
            continue
    return result


def pid_alive(pid):
    try:
        return bool(psutil.pid_exists(int(pid)))
    except (psutil.Error, OSError, ValueError, TypeError):
        return False


def process_uid(pid):
    """→ 进程属主用户名（str）或 None。"""
    try:
        return psutil.Process(int(pid)).username()
    except (psutil.Error, OSError, ValueError):
        return None


def origin_snapshot():
    """→ {pid: (ppid, args_str)}，供来源溯源。"""
    table = {}
    ppids = None
    if _ppid_map is not None:
        try:
            ppids = _ppid_map()
        except Exception:  # pragma: no cover
            ppids = None
    for proc in psutil.process_iter(attrs=["pid", "cmdline", "name"]):
        try:
            info = proc.info
        except (psutil.Error, AttributeError):
            continue
        pid = info.get("pid")
        if pid is None:
            continue
        if ppids is not None:
            ppid = ppids.get(pid)
            if ppid is None:
                continue
        else:
            try:
                ppid = proc.ppid()
            except psutil.Error:
                continue
        cl = info.get("cmdline")
        args = " ".join(cl) if isinstance(cl, list) else (info.get("name") or "")
        table[pid] = (ppid, args)
    return table


_ker = ctypes.WinDLL("kernel32", use_last_error=True)
_ker.CreateJobObjectW.restype = wintypes.HANDLE
_ker.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
_ker.AssignProcessToJobObject.restype = wintypes.BOOL
_ker.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
_ker.TerminateJobObject.restype = wintypes.BOOL
_ker.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
_ker.CloseHandle.argtypes = (wintypes.HANDLE,)
_ker.CloseHandle.restype = wintypes.BOOL

JOBS = {}
JOBS_GUARD = threading.Lock()

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def quote_cmd(s):
    """cmd.exe 安全引用：整体双引号包裹，内含双引号转义。"""
    return '"' + str(s).replace('"', '\\"') + '"'


def _create_job():
    return _ker.CreateJobObjectW(None, None)


def _assign(job, process_handle):
    return bool(_ker.AssignProcessToJobObject(job, process_handle))


def create_job_for(app_id, proc):
    """尝试把子进程放入 Job Object；失败时降级为仅进程树追踪。"""
    job = _create_job()
    if not job or not _assign(job, proc._handle):
        if job:
            _ker.CloseHandle(job)
        return None
    with JOBS_GUARD:
        JOBS[app_id] = job
    return job


def register_job(app_id, job):
    with JOBS_GUARD:
        JOBS[app_id] = job


def take_job(app_id):
    with JOBS_GUARD:
        return JOBS.pop(app_id, None)


def terminate_job(job):
    """终止 Job 内全部进程并关闭句柄；返回是否成功。

    句柄闭必须由调用者负责：Job 是操作系统内核对象，不关就泄漏。
    `take_job` 取出后所有权转移给此函数，调用方不应再 CloseHandle。
    """
    if not job:
        return False
    try:
        ok = bool(_ker.TerminateJobObject(job, 1))
    except Exception:
        ok = False
    finally:
        try:
            _ker.CloseHandle(job)
        except Exception:
            pass
    return ok


def spawn_command(command, cwd, token, env, log_fd, app_id):
    """启动 cmd 锚点进程；返回 (proc, job|None)。

    受控身份：config 记录 lastPid=cmd pid、runToken=token；运行判定用
    process_tree(lastPid)（锚点 + 后代树），停止用 Job Object 或 taskkill /T。

    `shell=True` 是必要的：原始 list 形式 `["cmd.exe", "/d", "/s", "/c", cmd]`
    在 `subprocess.list2cmdline` 转义后含 4 个引号，cmd.exe 解析 `/s` 时会剥离
    首尾引号，导致带内层引号的命令（如 `python -c "import sys"`）被破坏；
    `shell=True` 让 Popen 直接把 command 交给 cmd.exe，不再做 list2cmdline
    转义，cmd.exe 仍然作为锚点进程（Job Object / process_tree 仍基于此 pid）。
    """
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        command,
        cwd=cwd, stdout=log_fd, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=env, creationflags=flags,
        shell=True)
    job = create_job_for(app_id, proc)
    return proc, job


def process_tree(pid):
    """[anchor_pid] + 后代（递归）。缺进程/受限时只给 锚点或空。"""
    if not isinstance(pid, int) or pid <= 0:
        return []
    try:
        proc = psutil.Process(pid)
    except psutil.Error:
        return []
    members = [pid]
    try:
        members.extend(ch.pid for ch in proc.children(recursive=True))
    except psutil.Error:
        pass
    return members


def kill_tree(pid):
    """taskkill /T /F 兜底杀进程树；返回 (ok, error)。"""
    try:
        r = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True, text=True, errors="replace",
            timeout=5, creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0, None
    except Exception as e:
        return False, str(e)


def terminate_pids(pids, force):
    """终止一组 pid（先子后父）；force=True 用 kill()，否则 terminate()。

    Windows 上 `proc.terminate()` 与 `proc.kill()` 行为相同（TerminateProcess），
    仍保留分层语义供跨平台意图清晰。
    """
    killed = []
    for p in reversed(list(pids)):
        try:
            proc = psutil.Process(p)
            if force:
                proc.kill()
            else:
                proc.terminate()
            killed.append(p)
        except psutil.Error:
            continue
    return killed


# ---------------------------------------------------------------- 系统托盘

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
HWND_MESSAGE = -3
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40
MB_OK = 0x00000000
IDI_APPLICATION = 32512

TRAY_MENU = (
    (1, "打开面板", "open_panel"),
    (2, "停止", "stop"),
    (3, "退出", "quit"),
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_user32.MessageBoxW.restype = ctypes.c_int
_user32.MessageBoxW.argtypes = (
    wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)


def open_panel_url(host, port):
    """「打开面板」使用的浏览器地址。"""
    return "http://%s:%d/" % (host, port)


def message_box(title, text, flags=MB_ICONERROR):
    """无终端（windowed）下向用户展示致命错误，返回是否点了确定。"""
    return bool(_user32.MessageBoxW(None, text, title, flags))


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", _POINT),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_ubyte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM)

_user32.RegisterClassW.restype = wintypes.ATOM
_user32.RegisterClassW.argtypes = (ctypes.POINTER(_WNDCLASSW),)
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = (
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.DefWindowProcW.argtypes = (
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = (
    ctypes.POINTER(_MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_user32.TranslateMessage.argtypes = (ctypes.POINTER(_MSG),)
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(_MSG),)
_user32.PostMessageW.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = (
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.PostQuitMessage.argtypes = (ctypes.c_int,)
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.DestroyWindow.argtypes = (wintypes.HWND,)
_user32.LoadIconW.restype = wintypes.HICON
_user32.LoadIconW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR)
_user32.CreatePopupMenu.restype = wintypes.HMENU
_user32.AppendMenuW.restype = wintypes.BOOL
_user32.AppendMenuW.argtypes = (
    wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
_user32.TrackPopupMenu.restype = wintypes.BOOL
_user32.TrackPopupMenu.argtypes = (
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, ctypes.c_void_p)
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
_user32.GetCursorPos.argtypes = (ctypes.POINTER(_POINT),)
_user32.DestroyMenu.restype = wintypes.BOOL
_user32.DestroyMenu.argtypes = (wintypes.HMENU,)

_shell32.Shell_NotifyIconW.restype = wintypes.BOOL
_shell32.Shell_NotifyIconW.argtypes = (
    wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATAW))
_shell32.ExtractIconExW.restype = wintypes.UINT
_shell32.ExtractIconExW.argtypes = (
    wintypes.LPCWSTR, ctypes.c_int,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON),
    wintypes.UINT)

_ker.GetModuleHandleW.restype = wintypes.HMODULE
_ker.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)


class TrayIcon:
    """Windows 系统托盘：右键菜单「打开面板/停止/退出」，双击打开面板。"""

    def __init__(self, host, port, callbacks=None):
        self.host = host
        self.port = port
        self.callbacks = dict(callbacks or {})
        self._hwnd = None
        self._thread = None
        self._cb = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _dispatch(self, command_id):
        for item_id, _label, action in TRAY_MENU:
            if item_id == command_id:
                callback = self.callbacks.get(action)
                if callback is not None:
                    callback()
                return

    def _show_menu(self):
        menu = _user32.CreatePopupMenu()
        for item_id, label, _action in TRAY_MENU:
            _user32.AppendMenuW(menu, MF_STRING, item_id, label)
        point = _POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        _user32.SetForegroundWindow(self._hwnd)
        command = _user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
            point.x, point.y, 0, self._hwnd, None)
        _user32.DestroyMenu(menu)
        if command:
            self._dispatch(int(command))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_RBUTTONUP:
                self._show_menu()
            elif lparam == WM_LBUTTONDBLCLK:
                self._dispatch(1)
        elif msg == WM_COMMAND:
            self._dispatch(int(wparam & 0xFFFF))
            return 0
        elif msg == WM_DESTROY:
            _user32.PostQuitMessage(0)
            return 0
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _load_icon(self):
        big = wintypes.HICON()
        small = wintypes.HICON()
        exe = getattr(sys, "executable", None) or ""
        if exe:
            _shell32.ExtractIconExW(exe, 0, ctypes.byref(big),
                                    ctypes.byref(small), 1)
        icon = big.value or small.value
        if not icon:
            icon = _user32.LoadIconW(
                None, ctypes.cast(ctypes.c_void_p(IDI_APPLICATION),
                                  wintypes.LPCWSTR))
        return wintypes.HICON(icon)

    def _run(self):
        self._cb = _WNDPROC(self._wndproc)
        hinstance = _ker.GetModuleHandleW(None)
        wc = _WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(self._cb, ctypes.c_void_p)
        wc.hInstance = hinstance
        wc.lpszClassName = "ConsoleTrayWindow"
        wc.hIcon = self._load_icon()
        wc.hCursor = wc.hIcon
        _user32.RegisterClassW(ctypes.byref(wc))
        self._hwnd = _user32.CreateWindowExW(
            0, "ConsoleTrayWindow", "", 0, 0, 0, 0, 0, HWND_MESSAGE,
            None, hinstance, None)
        if not self._hwnd:
            LOG.warning("托盘创建失败：CreateWindowExW 未返回窗口句柄，继续运行（浏览器仍可用）。")
            return
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = wc.hIcon
        nid.szTip = "总控台"
        if not _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            LOG.warning("托盘创建失败：Shell_NotifyIconW(NIM_ADD) 失败，继续运行（浏览器仍可用）。")
            return
        msg = _MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        nid2 = _NOTIFYICONDATAW()
        nid2.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid2.hWnd = self._hwnd
        nid2.uID = 1
        _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid2))
        _user32.DestroyWindow(self._hwnd)

    def stop(self):
        if self._hwnd:
            _user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
            if self._thread is not None:
                self._thread.join(timeout=2.0)


def start_tray(host, port, callbacks):
    """创建并启动托盘图标，返回 TrayIcon 实例（供停止时调用 stop）。"""
    icon = TrayIcon(host, port, callbacks)
    icon.start()
    return icon
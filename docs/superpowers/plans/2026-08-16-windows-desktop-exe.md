# Windows 桌面端（单文件 exe + 系统托盘）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把总控台打包成免装 Python 的单文件 exe，并加系统托盘（右键「打开面板/停止/退出」、双击打开面板）。

**Architecture:** 在 `platform_win.py` 用 ctypes 直接调 Win32 `Shell_NotifyIcon` 实现托盘（零新增运行时依赖）；`server.py` 加 `--tray` 标志在端口绑定后启动托盘线程；PyInstaller 打包入口 `server.py --tray` 与 `static/` 为单文件 windowed exe。

**Tech Stack:** Python 3.12、psutil（运行时唯一第三方依赖）、ctypes/Win32（托盘）、PyInstaller（构建期）。

## Global Constraints

- 运行时零新增第三方依赖：只允许 `psutil`（托盘用 ctypes，不得引入 `pystray`/`Pillow` 等运行时库）。
- 托盘由 `--tray` 标志显式启用；未开启时行为与现状完全一致。
- 构建期依赖（`pyinstaller` + 固定版本 `psutil`）放 `requirements-build.txt`，不进运行时。
- exe 名用中文 `总控台.exe`；若 onefile 遇非 ASCII 打包问题，降级 ASCII 名 `Console.exe`。
- 不改 API 契约、配置 schema、进程管理语义。
- 测试命令：`python -m unittest tests.<module> -v`；全量用 `powershell -ExecutionPolicy Bypass -File tools/run_tests.ps1`。

---

## 文件结构

- Modify `platform_win.py` — 新增托盘常量/纯函数、`message_box`、`TrayIcon` 类、`start_tray`。
- Modify `server.py` — `parse_cli_args`、`main`/`_run_console` 加 `tray` 参数、端口绑定后启动托盘。
- Modify `tools/gen_brand_assets.py` — 生成 `console-app-icon.ico`（多尺寸）、`iconutil` 仅 macOS。
- Create `requirements-build.txt` — `pyinstaller` + 固定 `psutil`。
- Create `tools/build_exe.py` — PyInstaller 打包脚本。
- Test `tests/test_platform_win.py`（追加）、`tests/test_server.py`（追加）。

---

### Task 1: 托盘纯函数与常量（`platform_win.py`）

**Files:**
- Modify: `platform_win.py`（在模块尾部、`terminate_pids` 之后追加）
- Test: `tests/test_platform_win.py`（追加测试类）

**Interfaces:**
- Produces:
  - `TRAY_MENU`: `((1, "打开面板", "open_panel"), (2, "停止", "stop"), (3, "退出", "quit"))`
  - `open_panel_url(host, port) -> str`
  - `message_box(title, text, flags=MB_ICONERROR) -> bool`

- [ ] **Step 1: 写失败测试**

在 `tests/test_platform_win.py` 追加：

```python
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
```

（文件顶部需已有 `from unittest import mock`；若没有，追加 `import mock` 行。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_platform_win.TrayHelpersTests -v`
Expected: FAIL — `AttributeError: module 'platform_win' has no attribute 'TRAY_MENU'`。

- [ ] **Step 3: 实现**

在 `platform_win.py` 末尾追加：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_platform_win.TrayHelpersTests -v`
Expected: PASS（3 项）。

- [ ] **Step 5: 提交**

```bash
git add platform_win.py tests/test_platform_win.py
git commit -m "feat(windows): 托盘纯函数与常量"
```

---

### Task 2: `TrayIcon` 类与 `start_tray`（`platform_win.py`）

**Files:**
- Modify: `platform_win.py`（Task 1 的托盘段之后继续追加）
- Test: `tests/test_platform_win.py`（追加测试类）

**Interfaces:**
- Consumes: `TRAY_MENU`（Task 1）。
- Produces:
  - `TrayIcon(host, port, callbacks=None)`：`start()`（后台线程跑消息循环）、`stop()`（发 `WM_DESTROY` 退出循环）、`_dispatch(command_id)`（按 `TRAY_MENU` id 调用回调）。
  - `start_tray(host, port, callbacks) -> TrayIcon`：构造 `TrayIcon` 并 `start()`，返回实例。

- [ ] **Step 1: 写失败测试**

在 `tests/test_platform_win.py` 追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_platform_win.TrayIconTests -v`
Expected: FAIL — `AttributeError: module 'platform_win' has no attribute 'TrayIcon'`。

- [ ] **Step 3: 实现**

先在 `platform_win.py` 顶部 import 区补 `import sys`（`_load_icon` 需要 `sys.executable`），然后在托盘段之后继续追加（依赖 Task 1 已定义的 `_user32`/`_shell32`/常量）：

```python
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


def start_tray(host, port, callbacks):
    """创建并启动托盘图标，返回 TrayIcon 实例（供停止时调用 stop）。"""
    icon = TrayIcon(host, port, callbacks)
    icon.start()
    return icon
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_platform_win.TrayIconTests -v`
Expected: PASS（3 项）。

- [ ] **Step 5: 语法/导入自检**

Run: `python -c "import platform_win; print('ok')"`
Expected: `ok`（无 `AttributeError`/`TypeError`）。

- [ ] **Step 6: 提交**

```bash
git add platform_win.py tests/test_platform_win.py
git commit -m "feat(windows): Win32 系统托盘 TrayIcon"
```

---

### Task 3: `--tray` CLI 解析（`server.py`）

**Files:**
- Modify: `server.py`（`if __name__ == "__main__"` 之前新增 `parse_cli_args`；改写 `__main__` 的 `else` 分支）
- Test: `tests/test_server.py`（追加测试类）

**Interfaces:**
- Consumes: 无。
- Produces:
  - `parse_cli_args(argv) -> {"preferred_port": int|None, "open_browser": bool, "tray": bool}`

- [ ] **Step 1: 写失败测试**

在 `tests/test_server.py` 追加：

```python
class CliArgsTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(server.parse_cli_args([]),
                         {"preferred_port": None, "open_browser": True,
                          "tray": False})

    def test_no_browser_and_tray(self):
        self.assertEqual(server.parse_cli_args(["--no-browser", "--tray"]),
                         {"preferred_port": None, "open_browser": False,
                          "tray": True})

    def test_preferred_port(self):
        self.assertEqual(server.parse_cli_args(["--preferred-port", "9603"]),
                         {"preferred_port": 9603, "open_browser": True,
                          "tray": False})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_server.CliArgsTests -v`
Expected: FAIL — `AttributeError: module 'server' has no attribute 'parse_cli_args'`。

- [ ] **Step 3: 实现**

在 `server.py` 的 `if __name__ == "__main__":` 之前新增：

```python
def parse_cli_args(argv):
    """解析普通启动的 CLI 参数（--preferred-port / --no-browser / --tray）。"""
    preferred = None
    if "--preferred-port" in argv:
        index = argv.index("--preferred-port")
        try:
            preferred = int(argv[index + 1])
        except (ValueError, IndexError):
            raise SystemExit(2)
    return {
        "preferred_port": preferred,
        "open_browser": "--no-browser" not in argv,
        "tray": "--tray" in argv,
    }
```

并把 `__main__` 的 `else` 分支替换为：

```python
    else:
        args = parse_cli_args(sys.argv)
        main(preferred_port=args["preferred_port"],
             open_browser=args["open_browser"],
             tray=args["tray"])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_server.CliArgsTests -v`
Expected: PASS（3 项）。

- [ ] **Step 5: 提交**

```bash
git add server.py tests/test_server.py
git commit -m "feat(windows): 新增 --tray CLI 解析"
```

---

### Task 4: `main`/`_run_console` 集成托盘（`server.py`）

**Files:**
- Modify: `server.py`（`main` 与 `_run_console` 签名；端口绑定后启动托盘；端口全占时弹窗）
- Test: `tests/test_server.py`（追加测试类）

**Interfaces:**
- Consumes: `platform.start_tray(host, port, callbacks)`（Task 2）、`platform.message_box`（Task 1）、`parse_cli_args`（Task 3）。
- Produces: `main(preferred_port=None, open_browser=True, log_to_file=False, tray=False)`、`_run_console(preferred_port=None, open_browser=True, tray=False)`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_server.py` 追加：

```python
class TrayIntegrationTests(unittest.TestCase):
    def test_run_console_starts_tray_with_port(self):
        with mock.patch.object(server, "start_log_maintenance"), \
             mock.patch.object(server, "_ensure_private_dir"), \
             mock.patch.object(server, "open_browser_later"), \
             mock.patch.object(server, "Config"), \
             mock.patch.object(server, "platform") as platform, \
             mock.patch.object(server, "ConsoleServer") as console_cls:
            fake_server = console_cls.return_value
            platform.start_tray.return_value = mock.Mock()
            server._run_console(preferred_port=9600, open_browser=False,
                                tray=True)
            platform.start_tray.assert_called_once()
            args, kwargs = platform.start_tray.call_args
            self.assertEqual(args[0], server.HOST)
            self.assertEqual(args[1], 9600)
            fake_server.serve_forever.assert_called_once()
            platform.start_tray.return_value.stop.assert_called_once()
```

（注：`_run_console` 里托盘回调用 `server.shutdown` 会引用局部变量 `server`；测试里 `ConsoleServer` 被 mock，其 `return_value.shutdown` 存在即可。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_server.TrayIntegrationTests -v`
Expected: FAIL（`TypeError: _run_console() got an unexpected keyword argument 'tray'`）。

- [ ] **Step 3: 实现**

改 `_run_console`：

```python
def _run_console(preferred_port=None, open_browser=True, tray=False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for private_dir in (DATA_DIR, ICONS_DIR, LOGS_DIR):
        _ensure_private_dir(private_dir)
    start_log_maintenance()
    cfg = Config(CONFIG_PATH)

    server, port = None, None
    candidates = list(range(PORT_START, PORT_START + PORT_TRIES))
    if isinstance(preferred_port, int) and preferred_port in candidates:
        candidates.remove(preferred_port)
        candidates.insert(0, preferred_port)
    for p in candidates:
        try:
            server = ConsoleServer((HOST, p), Handler, cfg, p)
            port = p
            break
        except OSError:
            continue
    if server is None:
        message = "错误：端口 %d-%d 均被占用，无法启动。" % (
            PORT_START, PORT_START + PORT_TRIES - 1)
        print(message)
        if tray:
            platform.message_box("总控台", message)
        sys.exit(1)

    print("总控台已启动: http://%s:%d/  (Ctrl+C 停止)" % (HOST, port), flush=True)
    if open_browser:
        open_browser_later(port)

    tray_icon = None
    if tray:
        tray_icon = platform.start_tray(HOST, port, {
            "open_panel": lambda: open_browser_later(port),
            "stop": server.shutdown,
            "quit": lambda: os._exit(0),
        })
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if tray_icon is not None:
            tray_icon.stop()
        server.server_close()
        print("已停止", flush=True)
```

改 `main`：

```python
def main(preferred_port=None, open_browser=True, log_to_file=False, tray=False):
    """Run exactly one console for this project/data directory."""
    migration = prepare_runtime_storage()
    redirect_console_output()
    if migration["dataMigrated"]:
        print("已将项目内旧配置和图标复制到: %s" % DATA_DIR, flush=True)
    if migration["logsMigrated"]:
        print("已将项目内旧日志复制到: %s" % LOGS_DIR, flush=True)
    instance_lock = acquire_instance_lock()
    if instance_lock is None:
        print("总控台已在运行（同一数据目录只允许一个实例）。", flush=True)
        if open_browser:
            instances = find_console_instances()
            ports = [port for item in instances for port in item.get("ports", [])]
            if ports:
                webbrowser.open("http://%s:%d/" % (HOST, min(ports)))
        return False
    try:
        _run_console(preferred_port, open_browser, tray)
        return True
    finally:
        release_instance_lock(instance_lock)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_server.TrayIntegrationTests -v`
Expected: PASS。

- [ ] **Step 5: 全量回归**

Run: `powershell -ExecutionPolicy Bypass -File tools/run_tests.ps1`
Expected: 全部 PASS（含既有 156 项；托盘相关为新增）。

- [ ] **Step 6: 提交**

```bash
git add server.py tests/test_server.py
git commit -m "feat(windows): 服务端接入系统托盘"
```

---

### Task 5: 生成多尺寸 `.ico`（`tools/gen_brand_assets.py`）

**Files:**
- Modify: `tools/gen_brand_assets.py`（`main` 生成 `console-app-icon.ico`；`iconutil` 步骤改仅 macOS）
- Test: `tests/test_release.py`（若已有品牌资产测试，追加；否则用一次命令级冒烟）

**Interfaces:**
- Consumes: `static/assets/console-app-icon.png`（已存在）。
- Produces: `static/assets/console-app-icon.ico`（16/24/32/48/64/128/256）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_release.py` 追加（若无该文件，则在 `tests/test_platform_win.py` 追加）：

```python
class BrandAssetsTests(unittest.TestCase):
    def test_console_app_icon_ico_is_generated(self):
        ico = os.path.join(os.path.dirname(__file__), "..",
                           "static", "assets", "console-app-icon.ico")
        self.assertTrue(os.path.isfile(ico))
```

（该测试只是冒烟断言产物存在；真正的生成验证见 Step 3 的运行命令。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_release.BrandAssetsTests -v`（或对应文件）
Expected: FAIL — `console-app-icon.ico` 不存在。

- [ ] **Step 3: 实现**

改 `tools/gen_brand_assets.py`：

1. 在 `resized` 之后新增常量与生成逻辑；把 `main` 里 favicon 生成段落之后插入：

```python
    ico_path = ASSETS / "console-app-icon.ico"
    source.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )
```

2. 把 `main` 里 `iconutil = shutil.which("iconutil"); if not iconutil: raise SystemExit(...)` 及其后的 ICNS 生成整段包进 `if sys.platform == "darwin":`（并在文件顶部 `import sys`），非 macOS 直接跳过。

3. 更新末尾 `print` 段，新增一行打印 `console-app-icon.ico`。

- [ ] **Step 4: 运行生成脚本**

Run: `python tools/gen_brand_assets.py`
Expected: 无异常退出（Windows 上跳过 ICNS）；`static/assets/console-app-icon.ico` 已生成。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m unittest tests.test_release.BrandAssetsTests -v`（或对应文件）
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add tools/gen_brand_assets.py static/assets/console-app-icon.ico tests/test_release.py
git commit -m "feat(windows): 生成多尺寸 exe 图标 console-app-icon.ico"
```

---

### Task 6: PyInstaller 打包脚本与依赖（`tools/build_exe.py` + `requirements-build.txt`）

**Files:**
- Create: `requirements-build.txt`
- Create: `tools/build_exe.py`

**Interfaces:**
- Consumes: `static/assets/console-app-icon.ico`（Task 5）、`server.py`、`platform_win.py`、`static/`。
- Produces: `dist/总控台.exe`。

- [ ] **Step 1: 写 `requirements-build.txt`**

```text
# 仅构建期依赖：打包成 exe 用，不进运行时。
pyinstaller==6.11.1
psutil==7.2.2
```

（`psutil` 版本与运行时实际安装版本保持一致；先用 `python -c "import psutil; print(psutil.__version__)"` 确认。）

- [ ] **Step 2: 写 `tools/build_exe.py`**

```python
#!/usr/bin/env python3
"""用 PyInstaller 打包单文件 windowed exe（入口 server.py --tray）。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
ICON = STATIC / "assets" / "console-app-icon.ico"
DIST = ROOT / "dist"

DATA_FILES = [
    ("static/index.html", "static"),
    ("static/app.js", "static"),
    ("static/base.css", "static"),
    ("static/icons.js", "static"),
    ("static/js", "static/js"),
    ("static/themes", "static/themes"),
    ("static/assets", "static/assets"),
    ("static/fonts", "static/fonts"),
    ("static/icons", "static/icons"),
]


def build(name="总控台"):
    if not ICON.is_file():
        raise SystemExit("缺少图标：%s（先运行 tools/gen_brand_assets.py）" % ICON)
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", name,
        "--icon", str(ICON),
        "--hidden-import", "psutil",
    ]
    for src, dst in DATA_FILES:
        args += ["--add-data", "%s%s%s" % (src, os.pathsep, dst)]
    args.append(str(ROOT / "server.py"))
    subprocess.run(args, cwd=str(ROOT), check=True)
    print("已生成: %s" % (DIST / ("%s.exe" % name)))


if __name__ == "__main__":
    build()
```

- [ ] **Step 3: 安装构建依赖**

Run: `python -m pip install -r requirements-build.txt`
Expected: 成功安装 pyinstaller + psutil。

- [ ] **Step 4: 运行打包**

Run: `python tools/build_exe.py`
Expected: 无异常；`dist/总控台.exe` 生成。

- [ ] **Step 5: 冒烟验证（手工）**

双击 `dist/总控台.exe`：托盘出现图标 → 右键菜单三项 → 「打开面板」开浏览器 → 「停止/退出」结束进程。同时检查 `%LOCALAPPDATA%\总控台\logs\console.log` 有启动日志。

- [ ] **Step 6: 提交**

```bash
git add requirements-build.txt tools/build_exe.py
git commit -m "feat(windows): PyInstaller 单文件 exe 打包脚本"
```

---

## Self-Review 记录

- Spec 覆盖：spec §5.1→Task 1/2；§5.2→Task 3/4；§5.3→Task 5/6；§7 错误处理→Task 4（端口全占弹窗）；§8 测试→各 Task 的测试步骤 + 手工冒烟（Task 6 Step 5）。
- 无占位符：全部步骤含实际代码与命令。
- 类型一致：`TRAY_MENU`（Task 1）被 `TrayIcon`（Task 2）消费；`start_tray(host, port, callbacks)` 签名一致；`parse_cli_args`（Task 3）→ `main(..., tray=...)` → `_run_console(..., tray=...)`（Task 4）贯穿一致。

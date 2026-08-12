# 总控台 Windows 移植 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 macOS 专属的「总控台」移植为在 `C:\Users\Administrator\Desktop\local-ops-windows` 上可运行的 Windows 原生版本，保持与 mac 版相同的网页界面、API 契约与核心能力。

**Architecture:** 独立 Windows 变体（继承原仓库 git 历史）。`server.py` 的 HTTP/配置/前端逻辑基本不动，把系统交互（进程/端口/锁/对话框/启动器）改为 Windows 实现：进程数据面用唯一第三方依赖 `psutil`，受控进程用 `cmd.exe` 锚点 + Job Object + `taskkill` 进程树管理，文件锁用 `msvcrt`，原生对话框用 PowerShell。

**Tech Stack:** Python 3.12（标准库为主）、`psutil`（唯一第三方依赖）、PowerShell 5.1 内置命令、原生前端（零改动之外的少量文案与快捷键）。

## Global Constraints

- 只允许一个第三方依赖：`psutil`（`pip install psutil`）。其余一律 Python 3.12 标准库 + Windows 系统自带命令。
- 数据目录：配置+图标 `%APPDATA%\总控台\`；日志 `%LOCALAPPDATA%\总控台\logs\`。保留 `CONSOLE_DATA_DIR` / `CONSOLE_LOG_DIR` 覆盖。
- 端口区间 `120..129` 的绑定只有 `127.0.0.1`；从 9600 起，被占 +1，最多 10 个；`--no-browser` / `--preferred-port N` 参数保留。
- 配置 schema 与 `schemaVersion=1` 不变；`config.json.bak` 回滚与迁移机制保留。
- API 契约（`/api/state`、`/api/apps/*`、`/api/kill` 等）字段结构不变；`services[].origin`、`lastExit`、`health` 等语义不变。
- 去掉所有 `chmod`/`fchmod`/`os.getuid` 用法；进程归属改为「属主账户 == 当前用户账户」。
- 任务退出码协议不变：0=成功、130=取消、其他=失败。
- 前端文案不再出现「macOS / ps / lsof / osascript 原生框」。

---

### Task 1: 环境就绪：Python 3.12 + psutil + Windows 启动入口 + check.ps1

**Files:**
- Create: `start-hidden.vbs`
- Create: `start.bat`
- Create: `tools/run_tests.ps1`
- Modify: `Makefile`（保留，另加 `.PHONY: win-check`，内部不得调用 make）

**Interfaces:**
- Consumes: 无
- Produces: 运行时 `python server.py` 可执行；`start.bat` 前台运行；`start-hidden.vbs` 用 `pythonw` 静默后台运行；`tools/run_tests.ps1` 跑全部测试。

- [ ] **Step 1: 安装 Python 3.12 与 psutil**

在 PowerShell 中执行（如已安装则跳过；`python --version` 必须 ≥3.12）：

```powershell
winget install --id Python.Python.3.12 -e --silent
# 新装后重开 shell 或刷新 PATH
python --version
python -m pip install psutil
```

预期：`python --version` 输出 `Python 3.12.x`；`python -m pip show psutil` 存在。

- [ ] **Step 2: 创建 `start.bat`**

内容（保存为 UTF-8 无 BOM）：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
python server.py %*
```

- [ ] **Step 3: 创建 `start-hidden.vbs`**

```vbs
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run "pythonw.exe server.py", 0, False
```

- [ ] **Step 4: 创建 `tools/run_tests.ps1`**

```powershell
# 等价于 macOS 的 make check：
# 1) 语法/结构/生成文件检查  2) 单元测试
$ErrorActionPreference = "Stop"
python tools/check_project.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m unittest discover -s tests -p "test_*.py" -v
exit $LASTEXITCODE
```

- [ ] **Step 5: 修改 `Makefile` 增加 cross-platform 说明**

在 `Makefile` 末尾追加：

```make
# Windows：没有 make。请改用：
#   powershell -ExecutionPolicy Bypass -File tools/run_tests.ps1
```

- [ ] **Step 6: 运行测试确认环境可跑（先放宽为仅语法检查直跑 check_project.py）**

准备期先做最小验证：

```powershell
python tools/check_project.py --skip-tests
```

预期：<=499 行之间不报绝对错误（该工具当前仍引用 `总控台.app/Contents/Info.plist` 等 mac 资源，`--skip-tests` 跳过部分；全量适配放 Task 10）。

- [ ] **Step 7: 提交**

```bash
git add start.bat start-hidden.vbs tools/run_tests.ps1 Makefile
git commit -m "chore(windows): 启动入口与测试运行入口"
```

---

### Task 2: platform_win.py —— psutil 数据面

**Files:**
- Create: `platform_win.py`
- Test: `tests/test_platform_win.py`

**Interfaces:**
- Consumes: 无
- Produces（Task 3-9 用到的全部签名）：
  - `current_username() -> str`
  - `same_user(pid) -> bool`
  - `ps_snapshot(pids=None, with_uid=True) -> {pid: {"uid","comm","args","cpu","mem","etime"}}`（`uid` 为用户名 str）
  - `scan_listeners() -> {(pid, port): {bind_host, ...}}`（`pid` 为 None 的条目跳过）
  - `lsof_cwds(pids) -> {pid: cwd}`（拿不到返回空 dict）
  - `pid_alive(pid) -> bool`
  - `process_uid(pid) -> str|None`
  - `origin_snapshot() -> {pid: (ppid, args_str)}`

- [ ] **Step 1: 写失败测试 `tests/test_platform_win.py`**

```python
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
```

注意：`platform_win.py` 顶部 `import psutil` 在没装时会让该文件无法导入；测试同样依赖 psutil。

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m unittest tests.test_platform_win -v
```

预期：`ModuleNotFoundError: No module named 'platform_win'`

- [ ] **Step 3: 实现 `platform_win.py`（数据面完整版）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总控台 Windows 平台适配层（psutil 数据面）。

函数签名与 macOS 版一一对应，供 server.py 保持 HTTP/配置层不变。
psutil 是本移植唯一第三方依赖。
"""

import os
import time

import psutil


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
        p = psutil.Process(int(pid))
        return p.status() != psutil.STATUS_ZOMBIE
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
    for proc in psutil.process_iter(attrs=["pid", "ppid", "cmdline", "name"]):
        try:
            info = proc.info
        except (psutil.Error, AttributeError):
            continue
        pid, ppid = info.get("pid"), info.get("ppid")
        if pid is None or ppid is None:
            continue
        cl = info.get("cmdline")
        args = " ".join(cl) if isinstance(cl, list) else (info.get("name") or "")
        table[pid] = (ppid, args)
    return table
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m unittest tests.test_platform_win -v
```

预期：ALL PASS（`RUNNING OK`）。

- [ ] **Step 5: 提交**

```bash
git add platform_win.py tests/test_platform_win.py
git commit -m "feat(windows): psutil 数据面 platform_win.py"
```

---

### Task 3: 数据目录、实例锁与私有写入改 Windows

**Files:**
- Modify: `server.py`（顶部常量区 `L34-114`；`_ensure_private_dir`、`_copy_private_regular_file`、`write_private_bytes`、`acquire_instance_lock`、`release_instance_lock`、`register_console_insecure` 不涉及的均不动）
- Modify: `static/index.html` 之外无需动

**Interfaces:**
- Consumes: 无
- Produces: `server.SELF_UID` 为「当前用户名 str」；`INSTANCE_LOCK_PATH` 在数据目录；实例锁用 `msvcrt`。

- [ ] **Step 1: 改数据目录与运行标记**

编辑 `server.py` 顶部（当前 `DEFAULT_DATA_DIR`/`DEFAULT_LOGS_DIR` 在 `L37-39`），替换为：

```python
if sys.platform == "win32":
    _APPDATA = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    _LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    DEFAULT_DATA_DIR = os.path.join(_APPDATA, "总控台")
    DEFAULT_LOGS_DIR = os.path.join(_LOCALAPPDATA, "总控台", "logs")
else:
    DEFAULT_DATA_DIR = os.path.expanduser("~/Library/Application Support/总控台")
    DEFAULT_LOGS_DIR = os.path.expanduser("~/Library/Logs/总控台")

SELF_UID = platform.current_username() if sys.platform == "win32" else os.getuid()
```

`import platform_win as platform` 放在 `SELF_UID` 赋值之前（unittest 导入 server 时 platform_win 必须可用）。注意：`SELF_UID` 现在可能是 str（Windows）或 int（POSIX），原代码只做相等比较，类型一致即可。

- [ ] **Step 2: 私有目录/字节写函数去 chmod**

`_ensure_private_dir(path)`（约 `L179`）与 `write_private_bytes`（约 `L326`）中的 `os.chmod(...) / os.makedirs(mode=...)` 在 Windows 上无意义，替换为：

```python
def _ensure_private_dir(path):
    os.makedirs(path, exist_ok=True)

def write_private_bytes(path, payload):
    with open(path, "wb") as f:
        f.write(payload)
```

（跨平台保留原实现也可，但本项目 Windows 变体只面向 Windows，直接简化为如上标准库调用。）

- [ ] **Step 3: 实例锁改为 msvcrt**

替换 `acquire_instance_lock`（约 `L538`）与 `release_instance_lock`（约 `L570`）：

```python
def acquire_instance_lock(path=INSTANCE_LOCK_PATH):
    """单实例锁：文件偏移 0 处锁定 1 字节（msvcrt，跨进程有效）。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lock_file = open(path, "a+b")
        try:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lock_file.close()
            return None
        return lock_file
    except OSError:
        return None


def release_instance_lock(lock_file):
    try:
        if lock_file is not None:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    try:
        if lock_file is not None:
            lock_file.close()
    except OSError:
        pass
```

`import msvcrt` 加到文件顶部 import 区。删除 `import fcntl`（Windows 没有）。

- [ ] **Step 4: 去掉 `os.fchmod` 调用**

`start_app`（约 `L1515`）与 `redirect_console_output`（约 `L4005`）中的 `os.fchmod(...)` 在 Windows 抛异常，删除这两行。

- [ ] **Step 5: 冒烟测试**

创建 `tests/test_windows_runtime.py`：

```python
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
```

- [ ] **Step 6: 运行测试**

```bash
python -m unittest tests.test_windows_runtime -v
```

预期：`OK`；先确认 `server` 能成功 import（含 `platform_win` 与 `msvcrt`）。

- [ ] **Step 7: 提交**

```bash
git add server.py tests/test_windows_runtime.py
git commit -m "feat(windows): 数据目录、实例锁与私有写入适配"
```

---

### Task 4: 进程树与受控进程管理（启动/识别/停止）

**Files:**
- Modify: `platform_win.py`（追加 spawn/job/tree/kill）
- Modify: `server.py`（`build_launch_env`、`start_app`、`managed_process_index`/`_managed_candidates`、`pgid_members_map`、`resolve_app_stop_target`、`signal_app_stop`、`stop_pid_tree`、`stop_target_alive`、`_current_user_group_members`、`legacy_managed_pid`、`startup_failure_message`）
- Test: `tests/test_platform_win.py`（追加）、`tests/test_windows_runtime.py`（追加端到端）

**Interfaces:**
- Consumes: Task 2 的 `pid_alive`/`ps_snapshot`/`same_user`/`lsof_cwds`
- Produces:
  - `platform_win.spawn_command(command, cwd, token, env, log_fd, app_id) -> (Popen, job|None)`
  - `platform_win.process_tree(pid) -> [pid, ...descendants]`
  - `platform_win.terminate_job(job) -> bool`
  - `platform_win.kill_tree(pid) -> (ok, error)`
  - `platform_win.register_job(app_id, job)` / `platform_win.take_job(app_id) -> job|None`
  - `platform_win.quote_cmd(s) -> str`
  - `server` 侧保留原函数名：`start_app(app) -> (ok, error, proc, anchor_pid, token)`、`managed_pids(app)`、`kill_process(pid, force)`、`stop_pid_tree(pid, sig=None)`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_platform_win.py` 追加：

```python
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


def psutil_no_such_proc():
    import psutil
    return psutil.NoSuchProcess(999)
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m unittest tests.test_platform_win -v
```

预期：`AttributeError: ... process_tree`。

- [ ] **Step 3: platform_win.py 追加进程管理**

```python
import ctypes
import subprocess
from ctypes import wintypes

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
    if not job:
        return False
    try:
        return bool(_ker.TerminateJobObject(job, 1))
    except Exception:
        return False


def spawn_command(command, cwd, token, env, log_fd, app_id):
    """启动 cmd 锚点进程；返回 (proc, job|None)。

    受控身份：config 记录 lastPid=cmd pid、runToken=token；运行判定用
    process_tree(lastPid)（锚点 + 后代树），停止用 Job Object 或 taskkill /T。
    """
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        ["cmd.exe", "/d", "/s", "/c", command],
        cwd=cwd, stdout=log_fd, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=env, creationflags=flags)
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
```

`import threading` 加到 `platform_win.py` 顶部。

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m unittest tests.test_platform_win -v
```

预期：ALL PASS。

- [ ] **Step 5: server.py 侧改造（核心）**

以下专为 Windows 设计的替换（可用 `if sys.platform == "win32":` 保护；Windows 变体直接替换即可）：

**(a) `build_launch_env(token)`** —— 替换为 Windows PATH 注入：

```python
def build_launch_env(token, environ=None):
    env = dict(os.environ if environ is None else environ)
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    preferred = []
    for base in (appdata, local):
        preferred.append(os.path.join(base, "npm"))
        preferred.append(os.path.join(base, "Yarn", "bin"))
    preferred.extend([
        os.path.join(home, ".volta", "bin"),
        os.path.join(home, ".bun", "bin"),
        os.path.join(home, "scoop", "shims"),
        r"C:\Program Files\nodejs",
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
    ])
    preferred.extend(sorted(glob.glob(os.path.join(home, ".nvm", "versions", "node", "*")), reverse=True))
    choco = os.environ.get("ChocolateyInstall")
    if choco:
        preferred.append(os.path.join(choco, "bin"))
    preferred.extend((env.get("PATH") or "").split(os.pathsep))
    seen = set()
    env["PATH"] = os.pathsep.join(
        path for path in preferred if path and not (path in seen or seen.add(path)))
    env[RUN_TOKEN_ENV] = token
    return env
```

**(b) `start_app(app)`** —— 替换为：

```python
def start_app(app):
    _ensure_private_dir(LOGS_DIR)
    log_path = os.path.join(LOGS_DIR, "%s.log" % app["id"])
    rotate_log_file(log_path)
    cwd = app.get("cwd") or os.path.expanduser("~")
    try:
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        logf = os.fdopen(log_fd, "ab", buffering=0)
    except OSError as e:
        return False, "无法打开日志文件: %s" % e, None, None, None
    token = secrets.token_urlsafe(24)
    env = build_launch_env(token)
    try:
        header = "\n===== 启动于 %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S")
        logf.write(header.encode("utf-8"))
        proc, _job = platform_win.spawn_command(
            app["command"], cwd, token, env, log_fd, app.get("id") or "")
    except Exception as e:
        logf.close()
        return False, "启动失败: %s" % e, None, None, None
    logf.close()
    return True, None, proc, proc.pid, token
```

（`promote job` 会话内由 `create_job_for` 已登记，取用见下方 stop 路径。）

**(c) 受控进程识别** —— 替换 `pgid_members_map`、`_managed_candidates`、`managed_process_index`：

```python
def pgid_members_map():
    """Windows：无 pgid 概念，返回 {调用方便用的空 map}（保留调用点兼容）。"""
    return {}


def _managed_candidates(app, groups):
    pid = app.get("lastPid")
    if not isinstance(pid, int) or pid <= 0:
        return set()
    # lastPgid 在 Windows 上语义=锚点 pid 的别名，保留兼容。
    return set(platform_win.process_tree(pid))


def managed_process_index(apps, groups=None):
    """Windows 版：受控进程= 锚点 lastPid 的存活同用户进程树。"""
    candidates = {}
    all_pids = set()
    for app in apps:
        pids = _managed_candidates(app, groups)
        candidates[app["id"]] = pids
        all_pids.update(pids)
    snap = platform_win.ps_snapshot(all_pids) if all_pids else {}
    result = {}
    for app in apps:
        pid = app.get("lastPid")
        member = candidates.get(app.get("id")) or set()
        live = sorted(
            p for p in member
            if p in snap and snap[p].get("uid") == SELF_UID)
        if pid not in live:
            live = []
        result[app["id"]] = live
    return result, snap, {}
```

**(d) 停止路径** —— 替换 `stop_pid_tree`、`signal_app_stop`、`stop_target_alive`、`_current_user_group_members`（保留签名）：

```python
def stop_pid_tree(pid, sig=None):
    """终止受控进程树：优先 Job Object，回退 taskkill /T。"""
    job = platform_win.take_job(_app_id_by_anchor.get(pid))
    if platform_win.terminate_job(job):
        return True, None
    return platform_win.kill_tree(pid)


def signal_app_stop(target, sig=None):
    ident = target["id"]
    ok, err = stop_pid_tree(ident)
    return ok, err


def stop_target_alive(target, expected_uid=None):
    members = platform_win.process_tree(target["id"])
    return any(platform_win.same_user(m) for m in members)


def _current_user_group_members(pgid):
    return [p for p in platform_win.process_tree(pgid) if platform_win.same_user(p)]
```

为此需要在 server.py 里维护 `_app_id_by_anchor`: 一个 `{anchor_pid: app_id}` 的 module 级 dict（启动时登记、停止/删除时移除），并在 `stop_pid_tree` 使用前定义。在 `start_app` 成功后把 `app["id"] -> proc.pid` 写入。

简化实现：直接让 `stop_pid_tree` 接受 app_id；但调用点统一是 `resolve_app_stop_target` 返回的 `target["id"]`（即锚点 pid）。改用映射即可：

```python
_app_id_by_anchor = {}
def _remember_anchor(app_id, anchor_pid):
    _app_id_by_anchor[anchor_pid] = app_id
def _forget_anchor(anchor_pid):
    _app_id_by_anchor.pop(anchor_pid, None)
```

在 `start_app` 成功后、`persist_started_app` 前调用 `_remember_anchor(app["id"], proc.pid)`；在 `clear_app_runtime` 成功清理时调用 `_forget_anchor(old lastPid)`；`handle_app_delete` 后同样清理。新增时防竞态用 `MANUAL_STOP_LOCK` 之外简单 dict（会话内线程安全足够）。

**(e) `legacy_managed_pid`** —— 仅 `process_uid`/`lsof_cwds`/`SELF_UID` 语义已由平台层提供，函数体保持不变（注释里 mac 特定实现不变，行为等价）。

**(f) `kill_process(pid, force)`（约 L1424）** —— 需要看一眼现有实现后改造为：

```python
def kill_process(pid, force):
    if not platform_win.same_user(pid):
        return False, "该进程不属于当前用户，无法结束"
    try:
        proc = psutil.process(pid)
    except psutil.Error:
        return True, None
    members = platform_win.process_tree(pid)
    for p in reversed(members):
        try:
            proc=psutil.Process(p)
            proc.kill() if force else proc.terminate()
        except psutil.Error:
            continue
    return True, None
```

（需 `import psutil` 于 server.py 或改走平台层；推荐平台层再加 `platform_win.terminate_pids(pids, force)`。）

- [ ] **Step 6: 端到端测试追加 `tests/test_windows_runtime.py`**

```python
@unittest.skipUnless(WIN, "仅 Windows")
class SpawnStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="console-e2e-")
        self.cfg = {"apps": []}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spawn_tree_stop(self):
        app = {"id": "aabbccdd", "name": "srv",
               "command": "python -m http.server 8123",
               "cwd": self.tmp, "port": 8123, "kind": "service"}
        ok, err, proc, anchor, token = server.start_app(app)
        self.assertTrue(ok, err)
        deadline = time.time() + 10
        while time.time() < deadline:
            if server.managed_pids(app):
                break
            time.sleep(0.2)
        self.assertTrue(server.managed_pids(app))
        ok, err = server.stop_app_and_clear(self.cfg, app, timeout=10)
        self.assertTrue(ok, err)
        self.assertFalse(server.managed_pids({**app, "id": "aabbccdd"}))

    def test_task_exit_code_recorded(self):
        app = {"id": "11223344", "name": "task",
               "command": "python -c \"import sys; sys.exit(3)\"",
               "cwd": self.tmp, "port": None, "kind": "task"}
        ok, err, proc, anchor, token = server.start_app(app)
        self.assertTrue(ok, err)
        done = proc.wait(timeout=15)
        self.assertEqual(done, 3)
```

`stop_app_and_clear` 需要 cfg 对象是 `Config` 实例而非裸 dict；测试里用真实 `Config`：

```python
import server
from server import Config
cfg = Config(os.path.join(self.tmp, "config.json"))
```

（让测试通过 `Config` 构造，配置写盘路径放在 tmp 下。）

- [ ] **Step 7: 运行全部测试**

```bash
python -m unittest tests.test_windows_runtime tests.test_platform_win -v
```

预期：ALL PASS；进程能够启动、识别、停止。

- [ ] **Step 8: 提交**

```bash
git add platform_win.py server.py tests/test_platform_win.py tests/test_windows_runtime.py
git commit -m "feat(windows): cmd 锚点 + Job 树进程管理"
```

---

### Task 5: 进程溯源与分组规则

**Files:**
- Modify: `server.py`（`SYSTEM_PATH_PREFIXES`、`classify_group`、`_ORIGIN_*` 常量、`attribute_origin`、`origin_snapshot`、`build_watched`）
- Modify: `platform_win.py`

**Interfaces:**
- Consumes: Task 2 的 `origin_snapshot`
- Produces: 无新签名（行为一致）

- [ ] **Step 1: Windows 系统路径前缀**

替换 `SYSTEM_PATH_PREFIXES` 与 `classify_group` 里的路径判断（约 `L773, L791-797`）：

```python
SYSTEM_PATH_PREFIXES = (
    r"C:\Windows\System32", r"C:\Windows\SysWOW64", r"C:\Windows\",
    r"C:\Program Files\WindowsApps", r"C:\Program Files\Common Files\Microsoft",
    r"C:\Windows\WinSxS",
)


def classify_group(key, name, comm, args, cwd, promoted):
    if key in promoted:
        return "mine"
    text = name.lower()
    if any(k in text for k in DEV_KEYWORDS):
        return "mine"
    low_comm = (comm or "").lower()
    low_args = (args or "").lower()
    low_cwd = (cwd or "").lower()
    if any(low_comm.startswith(prefix.lower()) or
           low_comm.endswith(".exe") and prefix.lower() in low_comm
           for prefix in SYSTEM_PATH_PREFIXES):
        return "background"
    if any("\\appdata\\local\\temps" in low_comm or
           "\\windows\\" in low_comm):
        return "background"
    return "mine"
```

- [ ] **Step 2: 来源溯源 Windows 规则**

替换 `_ORIGIN_SKIP_NAMES`（约 `L818`）、`_ORIGIN_APP_ALIASES`（约 `L846`）、删 `_ORIGIN_BUNDLE_RE`（`.app` 只属于 mac）：

```python
_ORIGIN_SKIP_NAMES = {
    "svchost.exe", "explorer.exe", "dwm.exe", "conhost.exe", "cmd.exe",
    "powershell.exe", "pwsh.exe", "windowsappruntime.exe", "searchhost.exe",
    "rundll32.exe", "runtimebroker.exe", "taskhostw.exe",
}
_ORIGIN_APP_ALIASES = {
    "code.exe": ("VS Code", "code"),
    "cursor.exe": ("Cursor", "code"),
    "intellij idea.exe": ("IntelliJ IDEA", "code"),
    "clion.exe": ("CLion", "code"),
    "pycharm64.exe": ("PyCharm", "code"),
    "windows terminal.exe": ("Windows Terminal", "terminal"),
    "wt.exe": ("Windows Terminal", "terminal"),
}
_ORIGIN_MULTIPLEXERS = {}
```

注意 `_ORIGIN_AGENT_PATTERNS`（约 `L829`）保持不变，匹配的是命令行小写文本，跨平台同样有效。

`attribute_origin`（约 `L892`）内 `RUN_TOKEN_ARG_PREFIX in parent_args` 对 Windows 不再成立（token 走环境变量），增加一条先于其生效的规则：

```python
        if ppid == SELF_PID:
            return {"label": "总控台", "icon": "rocket"}
```

- [ ] **Step 3: build_watched 排除我们自己的命令**

`build_watched`（约 `L1007`）里 `name in ("ps", "lsof")` 改为平台无关：

```python
        if name in ("ps.exe", "lsof", "taskkill.exe", "cmd.exe"):
            continue
```

（更彻底：排除启动我方扫描进程的临时 command；可接受上述白名单近似。）

- [ ] **Step 4: 测试追加**

```python
class ClassifyTests(unittest.TestCase):
    def test_system_path_is_background(self):
        import server
        self.assertEqual(server.classify_group(
            "foo:1", "foo", r"c:\windows\system32\foo.exe",
            r"c:\windows\system32\foo.exe --x", None, set()), "background")

    def test_dev_keyword_is_mine(self):
        import server
        self.assertEqual(server.classify_group(
            "n:9", "python.exe", "python.exe", "python app.py",
            "C:\\a", set()), "mine")

    def test_origin_self_console(self):
        import server
        table = {1: (0, ""), server.SELF_PID: (1, "python server.py"),
                 41: (server.SELF_PID, "cmd.exe")}
        self.assertEqual(server.attribute_origin(41, table),
                         {"label": "总控台", "icon": "rocket"})
```

- [ ] **Step 5: 运行测试并提交**

```bash
python -m unittest tests.test_platform_win tests.test_windows_runtime -v
git add server.py platform_win.py tests/test_platform_win.py tests/test_windows_runtime.py
git commit -m "feat(windows): 进程溯源与分组规则的 Windows 适配"
```

---

### Task 6: 原生对话框与脚本命令（PowerShell + cmd 命令生成）

**Files:**
- Modify: `server.py`（`pick_path`、`command_for_script`、`SCRIPT_SUFFIXES`、`_simple_command_tokens`、`SHELL_BUILTINS`、`_script_target`）
- Modify: `static/js/overlays.js`（选择脚本/目录的后端正确使用 + 回退提示）

**Interfaces:**
- Consumes: 无
- Produces: `pick_path(what) -> (path|None, canceled)`；`command_for_script(path) -> str`（Windows 命令）；`SCRIPT_SUFFIXES` 覆盖 `.py/.ps1/.bat/.cmd/.sh/.bash`

- [ ] **Step 1: `pick_path` 改为 PowerShell 对话框**

替换 `pick_path`（约 `L1636`）：

```python
def pick_path(what):
    """Windows 原生目录/文件选择框（PowerShell WinForms）。返回 (path|None, canceled)。"""
    if what == "dir":
        body = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = '选择工作目录'; "
            "if ($f.ShowDialog() -ne 'OK') { exit 1 }; "
            "Write-Output $f.SelectedPath"
        )
    else:
        body = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            "$f.Filter = '脚本 (所有文件)|*.*'; "
            "if ($f.ShowDialog() -ne 'OK') { exit 1 }; "
            "Write-Output $f.FileName"
        )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
             "-Command", body],
            capture_output=True, text=True, errors="replace", timeout=180)
    except Exception:
        return None, False
    if r.returncode != 0:
        return None, True   # 用户取消
    out = (r.stdout or "").strip().strip('\x00')
    return out or None, False
```

- [ ] **Step 2: `command_for_script` 与后缀表**

替换 `command_for_script`（约 `L1652`）、`SCRIPT_SUFFIXES`（约 `L1669`）：

```python
def command_for_script(path):
    normalized = os.path.abspath(os.path.expanduser(str(path)))
    quoted = platform_win.quote_cmd(normalized)
    suffix = os.path.splitext(normalized)[1].lower()
    if suffix == ".py":
        return "python %s" % quoted
    if suffix == ".ps1":
        return "powershell -NoProfile -ExecutionPolicy Bypass -File %s" % quoted
    if suffix in (".bat", ".cmd"):
        return "call %s" % quoted
    if suffix in (".sh", ".bash"):
        return "bash %s" % quoted   # 需 PATH 里有 bash（如 Git Bash），否则 health 会提示
    if os.access(normalized, os.X_OK):
        return quoted
    return "bash %s" % quoted
```

```python
SCRIPT_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".sh", ".bash"}
```

- [ ] **Step 3: 命令解析与 builtin 表适配**

`SHELL_BUILTINS`（约 `L1670`）改为 cmd 内建：

```python
SHELL_BUILTINS = {
    "call", "cd", "chdir", "cls", "copy", "del", "dir", "echo", "endlocal",
    "exit", "for", "goto", "if", "md", "mkdir", "move", "path", "pause",
    "popd", "pushd", "rd", "rem", "ren", "rename", "rmdir", "set", "setlocal",
    "shift", "start", "time", "title", "type", "ver", "verify", "vol",
}
```

`_script_target`（约 `L1709`）里对 `python` 的识别：把 `python(?:\d+(?:\.\d+)*)?` 匹配批入可选 `py`，以及绝对路径脚本判定改为 Windows（`.bat/.cmd/.ps1` 直接运行）。同时把 `_simple_command_tokens`（约 `L1678`）的 `punctuation_chars="|&;<>()"` 保留（cmd 同样使用这些符号）。

- [ ] **Step 4: `os.access(path, os.X_OK)` 在 Windows 的坑**

Windows 上可执行性不体现在 X_OK；`_script_target` 中直接执行 `.bat/.cmd/.ps1` 命中即视为 direct；`.py` 转为 `python <脚本>`（非 direct）。保证 `inspect_app_health` 的「script-not-executable」检查在 Windows 不误报（`.bat` 恒不判定为不可执行）。实现上：`direct and not os.access(...)` 分支在 Windows 对 pure-file 直接跳过。

- [ ] **Step 5: 测试追加**

```python
@unittest.skipUnless(WIN, "仅 Windows")
class PickAndCommandTests(unittest.TestCase):
    def test_command_for_py(self):
        import server
        self.assertEqual(server.command_for_script(r"C:\a\b.py").split()[0], "python")
        self.assertIn("b.py", server.command_for_script(r"C:\a\b.py"))

    def test_quote_roundtrip(self):
        import platform_win
        self.assertEqual(platform_win.quote_cmd("a b c"), '"a b c"')
```

（`pick_path` 弹系统框无法单测；由 Task 9 手工验收。）

- [ ] **Step 6: 运行测试并提交**

```bash
python -m unittest tests.test_windows_runtime tests.test_platform_win -v
git add server.py tests/test_windows_runtime.py tests/test_platform_win.py
git commit -m "feat(windows): PowerShell 原生对话框与 cmd 命令生成"
```

---

### Task 7: 项目识别产出 Windows 命令

**Files:**
- Modify: `server.py`（`detect_project`、`_port_from_command` 相关）

**Interfaces:**
- Consumes: 无
- Produces: `detect_project` 产出能在 Windows cmd 下直接运行的命令（如 `python -m http.server 8000`、`npm run dev`、`python manage.py runserver`）

- [ ] **Step 1: Python 运行器改 Windows**

替换 `detect_project` 中两处 `python_runner`（约 `L2030`、`L2035`、`L2051`、`L2057`、`L2063`）：

```python
    python_runner = "python"   # Windows：python3 命令名不存在
```

以及静态站点兜底（约 `L2099`）：

```python
        add("python -m http.server 8000", "静态网站预览", "index.html", 8000, 90)
```

- [ ] **Step 2: 启动脚本识别改 Windows**

约 `L2088` 的候选脚本列表改为：

```python
    for script_name in ("start.bat", "dev.bat", "run.bat", "start.cmd",
                        "start.ps1", "start.sh", "dev.sh", "run.sh"):
        if os.path.isfile(os.path.join(root, script_name)):
            note_file(script_name)
            add(command_for_script(os.path.join(root, script_name)),
                "现有启动脚本", script_name, None, 70,
                "也可以继续使用“选择脚本”手动指定")
            break
```

- [ ] **Step 3: 测试追加**

```python
@unittest.skipUnless(WIN, "仅 Windows")
class DetectTests(unittest.TestCase):
    def test_static_site_hint(self):
        import server
        d = tempfile.mkdtemp(prefix="det-")
        try:
            open(os.path.join(d, "index.html"), "w").write("<html></html>")
            result, err = server.detect_project(d)
            self.assertIsNone(err)
            cmds = [c["command"] for c in result["candidates"]]
            self.assertIn("python -m http.server 8000", cmds)
        finally:
            shutil.rmtree(d, ignore_errors=True)
```

- [ ] **Step 4: 运行测试并提交**

```bash
python -m unittest tests.test_windows_runtime -v
git add server.py tests/test_windows_runtime.py
git commit -m "feat(windows): 项目识别生成 Windows 可执行命令"
```

---

### Task 8: 总控台自身重启/停止/launcher 适配

**Files:**
- Modify: `server.py`（`find_console_instances`、`_launcher_dialog`、`_launcher_alert`、`launcher_main`、`schedule_console_restart`、`restart_helper`、`redirect_console_output`、`main`）

**Interfaces:**
- Consumes: Task 2/3/4 的平台函数
- Produces: `--launcher`、`--restart-helper`、`--prepare-storage` 在 Windows 可用

- [ ] **Step 1: `find_console_instances` 保持不变**

它已走 `ps_snapshot`/`lsof_cwds`/`scan_listeners` 平台函数；`"server.py" in args` 在 Windows 的 cmdline 也是拼接字符串，无需改。只确认 `os.path.realpath` 对 Windows 路径正常工作（是）。

- [ ] **Step 2: `_launcher_dialog` / `_launcher_alert` 换 PowerShell 弹窗**

```python
def _launcher_dialog(message):
    body = (
        "$s = (New-Object -ComObject WScript.Shell).Popup("
        "'%s', 0, '总控台', 4 + 48); exit $s" % message.replace("'", "''")
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", body],
            capture_output=True, text=True, errors="replace", timeout=180)
    except Exception:
        return None
    # Popup 返回值：6=是/2=取消/7=否（4=是&否+取消 → 6 是 /7 否 /2 取消）
    return r.stdout.strip()
```

`_launcher_alert` 等价把 `_launcher_dialog` 抛进 try/except。`launcher_main` 中 `choice == "打开控制台"` / `"重新启动"` 的比较与 PowerShell 返回值不一致——将 `_launcher_dialog` 语义重定义为返回 `"Restart"|"Open"|None`：

```python
def _launcher_dialog(message):
    body = (
        "$r = (New-Object -ComObject WScript.Shell).Popup("
        "'%s', 0, '总控台', 4 + 48); "
        "if ($r -eq 6) { 'Restart' } elseif ($r -eq 7) { 'Open' }" %
        message.replace("'", "''")
    )
    ...
```

`launcher_main` 其余逻辑不变（`os.kill(pid, signal.SIGTERM)` 在 Windows 是 `TerminateProcess`，可用于旧实例退出；`signal` 模块常量可用）。保留 `process_uid == SELF_UID` 的同账户校验。

- [ ] **Step 3: `schedule_console_restart` 去掉 `start_new_session`**

`subprocess.Popen(..., start_new_session=True, ...)`（约 `L3929-3932`）在 Windows 无意义，替换为加 `platform_win.CREATE_NO_WINDOW`：

```python
    helper = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--restart-helper",
         str(SELF_PID), str(int(preferred_port))],
        cwd=BASE_DIR, close_fds=True,
        creationflags=platform_win.CREATE_NO_WINDOW)
```

- [ ] **Step 4: `restart_helper` 保持 `os.execv`**

`os.execv(sys.executable, args)` 在 Windows 上可行（替换当前进程）。不改。

- [ ] **Step 5: `redirect_console_output` 去掉 fchmod**

删 `os.fchmod(fd, 0o600)` 与 `os.open(..., 0o600)` 中的 mode（Windows 忽略 mode；保留 0o600 也不报错，但为一致去掉 fchmod 行即可）。

- [ ] **Step 6: 测试与手工验收**

命令行验收：
```bash
python server.py --no-browser
```
预期：启动后 `curl http://127.0.0.1:9600/api/health` 返回含 `"version"` 的 JSON；Ctrl+C 正常退出，`console.lock` 释放。

再验收 `--prepare-storage` 与 `--restart-helper`（手工）。

- [ ] **Step 7: 提交**

```bash
git add server.py
git commit -m "feat(windows): launcher/重启 helper 与启动入口适配"
```

---

### Task 9: 前端：快捷键与文案

**Files:**
- Modify: `static/app.js`（keybinding `L563-575`）
- Modify: `static/index.html`（`L118`、`L371`、`L462-465` 周边、`L8` description、`L498` `⌘V`）
- Modify: `static/opensearch` 等不涉及
- Modify: `static/js/widgets.js`（`L317`、`L338`）
- Modify: `static/themes/ops.css`（`L276` 注释）
- Modify: `static/js/overlays.js`（`L586` 注释、`L43` fallbackScriptCommand）

**Interfaces:**
- Consumes: 无
- Produces: 用户在 Windows 按 Ctrl+K / Ctrl+J 可用

- [ ] **Step 1: 快捷键兼容 Ctrl（不改回退 mac ⌘）**

`static/app.js` `L565` 与 `L573` 已是 `e.metaKey || e.ctrlKey`，**无需改动**。改为明确注释并确保无遗漏；在 index.html 的 `<kbd>` 或提示文案中改为同时显示平台按键：

- `L118` 附近命令面板触发键：改为动态或直接标注 `Ctrl K`（Windows）/ `⌘K`（mac）。简化：文案统一为 `⌘K / Ctrl+K`。

- [ ] **Step 2: 文案替换**

- `index.html L8`：`description` 改为「本地服务与批处理任务的快速启动、运行监测工具（Windows）」。
- `index.html L498`：`⌘V` 粘贴提示改为「也可 Ctrl+V / ⌘V 粘贴剪贴板图片」。
- `overlays.js L586`：注释「浏览工作目录（macOS 原生选择框）」→「浏览工作目录（系统原生选择框）」。
- `overlays.js L43` `fallbackScriptCommand`：把 `python3` 相关命令改为 `python`（如适用）。

- [ ] **Step 3: 术语清理（服务/消息/前端）**

搜索并替换静态目录中剩余的 `lsof`、`osascript`、`ps/lsof`、`\b3\.x?` 等，仅保留中文提示不可见的内部名。确保前端无「macOS」字样。

- [ ] **Step 4: 提交**

```bash
git add static
git commit -m "feat(windows): 前端快捷键与平台文案适配"
```

---

### Task 10: 测试移植 + 冒烟测试 + check.ps1

**Files:**
- Modify: `tests/test_server.py`、`tests/test_hardening.py`（适配 Windows 断言、删 `os.killpg`/`osascript` 依赖的用例或改为 mock）
- Modify: `tests/test_project_checks.py`、`tests/test_release.py`、`tests/test_frontend.py`（`总控台.app`、Info.plist 相关改为 Windows 免责）
- Modify: `tools/check_project.py`（Windows 免 `plistlib`、免 `总控台.app`，改为检查 `start.bat`/`start-hidden.vbs`）
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: 全部平台函数
- Produces: `python -m unittest discover -s tests -p 'test_*.py'` 全绿；`tools/run_tests.ps1` 全绿

- [ ] **Step 1: 跑一遍现有测试，逐个修**

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

对照失败点处理：
- 引用 `os.killpg` / `os.getpgid` → 改用 `platform_win`/mock；
- 引用 `osascript`、`总控台.app`、`Info.plist` → 按 Windows 语义改写或跳过（`@unittest.skipIf(sys.platform == "win32", ...)`）；
- `test_release.py` 的发行包边界检查若针对 mac 产物，可保留但标注 Windows 变体不发布，改为专注源码检查。

- [ ] **Step 2: 追加冒烟 `tests/test_smoke.py`**

覆盖：`GET /api/health`、`GET /api/state` 结构、启动一个简单 HTTP 服务后再 `stop`，幂等删除。用真实 `ThreadingHTTPServer` 起临时 server（参考现有 test_server 的方法），端口用随机高位避开 9600 冲突。

- [ ] **Step 3: `tools/check_project.py` 平台降级**

- `INFO_PLIST` 路径缺失时 `--skip-tests` 之外的 「Info.plist」 检查在 Windows 跳过（`sys.platform == "win32"` 时 return OK）。
- 资源引用检查改为不依赖 `.app`。
- `VERSION` / 语法 / 图标同步检查保留。

- [ ] **Step 4: 运行**

```bash
powershell -ExecutionPolicy Bypass -File tools/run_tests.ps1
```

预期：exit 0。

- [ ] **Step 5: 提交**

```bash
git add tests tools/check_project.py
git commit -m "test(windows): 移植测试套件并新增冒烟测试"
```

---

### Task 11: README / AGENTS.md 文档与最终验收

**Files:**
- Modify: `README.md`（Windows 安装/运行/数据目录/限制）
- Modify: `AGENTS.md`（Windows 实现要点与平台函数映射）

**Interfaces:**
- Consumes: 全部
- Produces: 文档与运行说明与实现一致

- [ ] **Step 1: README 更新**

在 README 顶部注明本仓库是 Windows 变体；「安装」改为：装 Python 3.12、`pip install psutil`、双击 `start.bat` 或 `start-hidden.vbs`；系统要求改为 Windows 10/11；数据目录改为 `%APPDATA%\总控台` 与 `%LOCALAPPDATA%\总控台\logs`；并写明已知取舍（cwd 受限、通知弹窗、Job 近似进程组）。

- [ ] **Step 2: AGENTS.md 更新**

记录：平台层在 `platform_win.py`；psutil 是唯一依赖；受控进程=cmd 锚点+Job/树；停止=Job→taskkill；对话框/通知=PowerShell；`SELF_UID` 是用户名 str；测试命令 `python -m unittest ...` 与 `tools/run_tests.ps1`。

- [ ] **Step 3: 端到端验收**

```bash
start-hidden.vbs        # 或 python server.py
# 浏览器打开 http://127.0.0.1:9600/
```

验收清单（对应 spec 验收标准）：
1. 添加服务：`python -m http.server 8123`（工作目录任选存在目录）→ 启动成功、卡片变运行中、端口可见。
2. 停止/重启正常；日志中心能看到日志。
3. 服务监控出现该监听端口；启动者徽标为「总控台」。
4. 「新端口发现」加入启动台（从服务监控点「加入启动台」）成功且 pid 认领。
5. 添加任务：`python -c "import sys;sys.exit(3)"` → 运行后显示失败（exit 3）。
6. Ctrl+K 打开命令面板；Ctrl+J 打开日志中心。
7. 快捷操作「停止全部」仅停总控台受控进程。
8. `tools/run_tests.ps1` 全绿。

- [ ] **Step 4: 提交**

```bash
git add README.md AGENTS.md
git commit -m "docs(windows): 更新 README 与 AGENTS 为 Windows 变体"
```

---

## Self-Review（写计划后自查）

- Spec 覆盖：环境/启动入口(T1)、数据/锁(T3)、端口与进程数据面(T2)、启动/识别/停止(T4)、溯源与分组(T5)、对话框与脚本命令(T6)、项目识别(T7)、总控台自管理(T8)、前端(T9)、测试与 smoke(T10)、文档与验收(T11)。无缺项。
- 占位符：无 TBD/TODO；所有代码步骤都给出完整代码或精确修改点。
- 类型一致：`managed_process_index` 返回 `(index, snap, groups)` 三元素与既有调用一致；`start_app` 返回 `(ok, error, proc, pgid, token)` 与既有调用一致；`SELF_UID` 在 Windows 为 str、`ps_snapshot`/`process_uid` 返回用户名 str 保持相等比较。
- 风险提示：`start_new_session`（Task8 已处理）、`os.fchmod`（Task3 已处理）、`CREATE_NO_WINDOW` 下无法用 CTRL_BREAK 温和停机（文档写明）。
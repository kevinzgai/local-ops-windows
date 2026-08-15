#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总控台 Windows 平台适配层（psutil 数据面）。

函数签名与 macOS 版一一对应，供 server.py 保持 HTTP/配置层不变。
psutil 是本移植唯一第三方依赖。
"""

import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes

import psutil

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
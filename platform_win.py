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
"""Windows 平台判定与跳过装饰器的公共定义。

各测试文件统一从这里导入，避免重复定义：

    try:
        from _win import IS_WINDOWS, skip_windows
    except ImportError:  # python -m unittest tests.test_xxx 运行方式
        from tests._win import IS_WINDOWS, skip_windows

本模块不以 test_*.py 命名，unittest discover 不会把它当作测试模块。
"""

import sys
import unittest

IS_WINDOWS = sys.platform == "win32"
skip_windows = unittest.skipIf(
    IS_WINDOWS, "macOS-only (Unix 语义：shell 运行期 / .app / 信号 / 进程组 / 符号链接 / 权限位)")


def other_uid(uid):
    """构造一个不同于给定 uid 的值（Windows 为用户名 str，macOS 为 int）。"""
    return "other-user" if isinstance(uid, str) else uid + 1


def long_running_command():
    """跨平台的长驻进程命令（Windows cmd 没有 Unix 的 sleep 命令）。"""
    return '"%s" -c "import time; time.sleep(20)"' % sys.executable

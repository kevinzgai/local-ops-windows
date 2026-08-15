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
    ("VERSION", "."),
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


def build_args(name="总控台"):
    """构造 PyInstaller 命令行（纯函数，便于单元测试）。"""
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
    return args


def build(name="总控台"):
    if not ICON.is_file():
        raise SystemExit("缺少图标：%s（先运行 tools/gen_brand_assets.py）" % ICON)
    subprocess.run(build_args(name), cwd=str(ROOT), check=True)
    spec = ROOT / ("%s.spec" % name)
    if spec.is_file():
        spec.unlink()
    exe = DIST / ("%s.exe" % name)
    print("已生成: %s" % exe)
    return exe


if __name__ == "__main__":
    build()

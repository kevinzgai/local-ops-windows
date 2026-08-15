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

# Windows 桌面端（单文件 exe + 系统托盘）设计

- 日期：2026-08-16
- 状态：已评审（待实现）
- 关联：Windows 变体（`feat/windows-port`），macOS 原版见 `laogou717/local-ops`

## 1. 背景与目标

总控台目前是「本地 Python 服务 + 浏览器前端」，用户需自装 Python 3.12 并 `pip install psutil`，且只能通过浏览器或命令行启停。本设计把它做成 **Windows 桌面端**：

1. **免安装 exe**：用 PyInstaller 把后端 + psutil + 前端打成单个可执行文件，双击即用，无需安装 Python 或任何依赖。
2. **单文件便携分发**：`onefile` 模式，一个 `总控台.exe` 可拷贝即用。
3. **系统托盘**：托盘图标 + 右键菜单「打开面板 / 停止 / 退出」，提供桌面级启停入口。

## 2. 非目标

- **不引入原生窗口**：UI 仍是浏览器页面，不做 WebView/Electron 内嵌窗口。
- **不做安装包 / 代码签名**：本阶段只出便携 exe；安装包、签名、自动更新留待后续。
- **不改变 API 契约、配置 schema、进程管理语义**：仅新增分发与托盘层，运行时行为（端口扫描、受控进程、停止策略）不变。
- **不改动源码开发形态**：`python server.py`、`start.bat`、`start-hidden.vbs` 保留不变。

## 3. 约束

- **运行时零新增依赖**：打包进 exe 的运行时依赖仍只有 `psutil`。托盘用 ctypes 直接调 Win32，不引 `pystray`/`Pillow` 等运行时库。
- **构建期依赖**：`pyinstaller` 与固定版本的 `psutil` 放 `requirements-build.txt`，不进运行时。
- **源码模式不受影响**：托盘由 `--tray` 标志显式启用；未开启时行为与现状完全一致。

## 4. 架构

```
总控台.exe（PyInstaller onefile, windowed）
  └─ 入口 server.py --tray
       ├─ prepare_runtime_storage()
       ├─ redirect_console_output()        # tee 到 %LOCALAPPDATA%\总控台\logs\console.log
       ├─ acquire_instance_lock()          # 单实例（msvcrt）
       ├─ 绑定 127.0.0.1:9600+（被占则 +1，最多 10）
       ├─ 启动托盘线程（传入实际 port）      # platform_win 新增
       ├─ 自动打开浏览器
       └─ serve_forever()
```

## 5. 组件设计

### 5.1 系统托盘（`platform_win.py` 新增，纯 ctypes）

- 新增 `TrayIcon` 类与 `start_tray(port, callbacks)` 入口。
- Win32 API：
  - `Shell_NotifyIconW`（`NIM_ADD` / `NIM_MODIFY` / `NIM_DELETE`）管理图标。
  - `NOTIFYICONDATAW` 结构（含 `cbSize`、`hWnd`、`uID`、`uFlags`、`hIcon`、`szTip`、`uCallbackMessage`）。
  - 隐藏消息窗口：`RegisterClassW` + `CreateWindowExW(..., HWND_MESSAGE, ...)`，回调消息 `WM_APP + 1`。
  - 消息循环：后台线程 `GetMessageW` / `TranslateMessage` / `DispatchMessageW`。
  - 右键菜单：`CreatePopupMenu` + `AppendMenuW` + `TrackPopupMenu`；菜单项 `打开面板` / `停止` / `退出`。
  - 图标句柄：`ExtractIconExW` 从 exe 自身嵌入资源（`--icon` 已写入）取 HICON；兜底 `LoadImageW` 加载打包内 `static/assets/console-app-icon.ico`。
- 交互：
  - 左键双击图标 → 打开面板。
  - 右键 → 弹菜单；选「打开面板」→ 打开面板；「停止」→ 触发停止回调；「退出」→ 触发退出回调。
- 线程安全：托盘线程只发信号（调用传入的回调），不直接触碰 HTTP 服务；主线程负责真正 shutdown。

### 5.2 `server.py` 集成

- 新增 CLI 标志 `--tray`（`if __name__ == "__main__"` 的 `else` 分支解析）。
- `_run_console` 在 `serve_forever` 前：若启用托盘，调用 `start_tray(port, callbacks)`，回调绑定：
  - `open_panel` → `webbrowser.open("http://127.0.0.1:%d/" % port)`。
  - `stop` → 触发 `server.shutdown()`（优雅停止；服务停后进程随之退出，等价网页「停止总控台」）。
  - `quit` → `os._exit(0)`（立即结束，跳过优雅清理，兜底）。
- 单实例：复用现有 `msvcrt` 锁。锁失败时（第二实例）打开已有实例面板后退出，不重复启动托盘。
- 端口传递：`start_tray` 收到绑定成功的实际端口（9600 起可能 +1），「打开面板」用真实端口。

### 5.3 打包（PyInstaller）

- 新增 `tools/build_exe.py`：封装 PyInstaller 调用，参数 `--onefile --windowed --name 总控台 --icon static/assets/console-app-icon.ico`。
  - 入口脚本：`server.py`，运行参数追加 `--tray`。
  - 数据文件：`static/`（js、css、themes、fonts、assets、icons.js、index.html）。
  - 隐藏导入：`psutil` 及其 C 扩展。
- 新增 `requirements-build.txt`：`pyinstaller` + 固定版本 `psutil`（与运行时一致）。
- 产物：`dist/总控台.exe`。
- 图标：扩展 `tools/gen_brand_assets.py`：
  - 从 `static/assets/console-app-icon.png` 生成 `static/assets/console-app-icon.ico`，尺寸 16/24/32/48/64/128/256。
  - 原 `iconutil` 生成 macOS `AppIcon.icns` 的步骤改为「非 macOS 跳过」（当前在 Windows 上会 `SystemExit`）。

## 6. 数据流

1. 双击 `总控台.exe`。
2. 入口 `server.py --tray`：prepare → redirect console output → acquire lock → 绑定端口 → 启动托盘 → 开浏览器 → `serve_forever`。
3. 托盘菜单「打开面板」→ `webbrowser.open` 用真实端口。
4. 托盘菜单「停止」→ 主线程 `server.shutdown()` → `serve_forever` 返回 → 进程退出。
5. 托盘菜单「退出」→ `os._exit(0)`。
6. 所有 stdout/stderr 经 `redirect_console_output` tee 到 `console.log`（托盘动作也记录日志）。

## 7. 错误处理

- 托盘创建失败（罕见，如 shell 异常）：记 `console.log` 警告，继续运行（浏览器仍可用，靠网页「停止」退出）。
- windowed 模式下致命启动错误（端口 9600–9609 全占、实例锁异常）：弹 `MessageBox` 告知（不依赖终端），随后退出。
- `--tray` 未开启时：任何托盘相关代码不执行，行为与现状一致。

## 8. 测试策略

- 单测（不碰真实 Win32 窗口）：
  - 托盘菜单项 → 动作的映射（抽成纯函数）。
  - `start_tray` 回调（`open_panel` 的 URL 拼接、`stop`/`quit` 信号）用 mock 校验。
  - `--tray` 标志解析。
- 现有测试套件（`tools/run_tests.ps1` / `make check`）全量通过；托盘默认关闭，测试不受影响。
- 构建验证：`tools/build_exe.py` 产出 `dist/总控台.exe`；手工冒烟（双击 → 托盘出现 → 打开面板 → 停止/退出）。

## 9. 决策记录

- exe 名用中文 `总控台.exe`；若 PyInstaller onefile 遇非 ASCII 打包问题，降级为 ASCII 名（如 `Console.exe`）。
- 托盘菜单「停止」= 优雅停服务（≈退出）、「退出」= 立即强制退出；二者功能接近，保留两个入口以区分优雅/强制。
- 构建期依赖 `pyinstaller` 放 `requirements-build.txt`，不进运行时。
- 打包工具选 PyInstaller（onefile + windowed），暂不评估 Nuitka（杀软误报问题后续再议）。

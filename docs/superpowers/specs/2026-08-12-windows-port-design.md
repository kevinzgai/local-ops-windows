# 总控台 Windows 移植设计方案

日期：2026-08-12
状态：已批准

## 背景与目标

把 macOS 专属的「总控台」（local-ops）移植为独立的 Windows 变体，保持相同的网页界面、
API 契约与核心能力：启动台、服务监控、日志中心、命令面板、主题、端口发现、进程溯源、
配置诊断。macOS 原仓库保持不动，仅作参考。

已确认的决策：

- 允许使用唯一的第三方依赖 `psutil`；其余仍用 Python 3 标准库。
- 功能范围：完整功能移植。
- 代码组织：独立 Windows 变体（新目录 `C:\Users\Administrator\Desktop\local-ops-windows`，继承 git 历史）。
- 环境：由本会话使用 winget 安装 Python 3.12 并 `pip install psutil`，用于本地运行与验证。

## 环境与启动入口

- 安装：`winget install Python.Python.3.12`（加入 PATH），随后 `pip install psutil`。
- 启动入口：
  - `start.bat` —— 前台运行 `python server.py`，能在终端看实时输出（等价 mac 的 `start.command`）。
  - `start-hidden.vbs` —— 用 `pythonw.exe` 静默后台运行，无控制台窗口（等价 mac 的 `总控台.app`）。
  - `python server.py` —— 命令行调试入口，等价 mac 原入口。
- 端口策略不变：绑定 `127.0.0.1`，从 9600 起试，被占 +1（最多 10 个），自动打开浏览器。
- 可选参数不变：`--no-browser`、`--preferred-port N`。

## 数据与日志位置

- 配置 + 图标：`%APPDATA%\总控台\`（恒等于 `os.environ["APPDATA"]\总控台`）。
- 日志：`%LOCALAPPDATA%\总控台\logs\`。
- 保留 `CONSOLE_DATA_DIR` / `CONSOLE_LOG_DIR` 环境变量覆盖与防误用校验（拒绝空值、
  相对路径、`C:\`、用户主目录、项目根）。
- Windows 无 0700/0600 语义：去掉 chmod/fchmod，改为在应用层检查数据目录位于用户
  profile 之下；不做 icacls 收紧（默认 per-user 隔离已足够，文档注明）。
- 配置 schema 与 `schemaVersion=1` 不变，`config.json.bak` 回滚机制保留。

## macOS → Windows 平台映射

### 文件锁

- `fcntl.flock`（实例锁 + 配置写锁的跨进程保护）→ `msvcrt.locking`：打开锁文件后对
  偏移 0 处 1 字节做 `LK_NBLCK`/`LK_UNLCK`。实例锁行为（单实例、失败即退出）保持不变。

### 监听端口快照

- `lsof -iTCP -sTCP:LISTEN -P -n` → `psutil.net_connections(kind="tcp")`，过滤
  `status == "LISTEN"`，产出 `{(pid, port): {bind_host, ...}}`，`(pid, port)` 去重映射
  不变（IPv4/IPv6 各一条）。绑定地址提取自 `laddr`。

### 进程快照

- `ps` → `psutil.process_iter(attrs=[...])`：
  - `pid`、`name`（≈comm）、`cmdline`（≈args）、`create_time`（换算 `etime`）、
    `memory_percent`、`cpu_percent`（无间隔首次调用返回 0.0，接受此误差）。
  - `uid` 概念 → 用「进程属主账户 == 当前用户账户」判定归属，API 输出保持不变
    （`services[].origin` 等字段结构不变）。
- `pid_alive` → `psutil.pid_exists(pid)`。

### 进程工作目录

- `lsof -a -p ... -d cwd -Fn` → `psutil.Process(pid).cwd()`（需要 `self.cwd()` 影响目标进程
  处理：受限/无权限进程抛 `AccessDenied`/`ZombieProcess` 时返回 None，调用方降级为
  「未知目录」，只影响展示与分组，不阻断功能）。
- cwd 为空时服务监控「目录」列显示占位文案（如「未知（受限）」），不参与项目识别。

### 进程归属与分组

- `classify_group` 的 Windows 版：
  - `promoted` → `mine`；
  - 进程名命中 `DEV_KEYWORDS`（同原列表）→ `mine`；
  - 系统目录内（`C:\Windows\System32\`、`C:\Windows\`、`C:\Program Files\WindowsApps\`、
    `C:\Program Files\Common Files\Microsoft\`）→ `background`；
  - 其余默认 `mine`。
- `SYSTEM_PATH_PREFIXES` 改为 Windows 系统路径前缀表。

### 进程溯源徽标

- `attribute_origin` 沿 `ppid` 链（≤12 层，psutil `Process(pid).ppid()` / `parent()`）识别：
  - 已知 AI 助手（codex/claude/kimi/gemini/aider/opencode 等，按进程名/命令行小写匹配）；
  - 已知终端/编辑器 `.exe`：`Code.exe`、`Cursor.exe`、`WindowsTerminal.exe`、`cmd.exe`、
    `powershell.exe`、`pwsh.exe` 等；
  - 总控台自身标记（启动参数含 `console-run:` token）；
  - 未识别则取最近的非系统祖先进程名。
- `icon` 取值映射与 mac 一致（bot/code/terminal/package/rocket/server）。

### 进程启动、识别与停止（核心差异）

- 启动：`subprocess.Popen(["cmd.exe", "/d", "/s", "/c", inner], cwd=..., creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_UNICODE_ENVIRONMENT, startupinfo=隐藏窗口, env=build_launch_env(token))`。
  - `inner` 为原始用户命令，`cmd /c` 同步等待其退出，作为锚点进程（等价 mac 外层 bash）。
  - token 以 `rem console-run:<token>` 注释形式出现在 `cmd` 命令行内，便于会话内溯源；
    同时 token 写入 config（同 mac），并写入进程环境变量 `CONSOLE_RUN_TOKEN`。
- 受控进程识别（running 判定）：
  - 主路径：config `lastPid` 指向锚点 cmd；存活判定 = 锚点存活 或 以锚点为根的后代树
    （`psutil.Process(lastPid).children(recursive=True)`）仍有存活。
  - 会话内额外维护 Job Object 句柄（见停止），重启总控台后句柄丢失时退回上面的树识别。
  - token 溯源：会话内按「命令行含 `rem console-run:<token>`」兜底匹配。
- 停止：
  - 首选：ctypes 调用 `CreateJobObject` / `AssignProcessToJobObject`，将启动的子进程
    放入 Job Object，停止时 `TerminateJobObject`，保证整棵进程树被杀（等价 killpg）。
  - 回退：`taskkill /T /F /PID <锚点>`（树内杀）。
  - 温和停止（SIGTERM 等价）在 Windows 不可靠：隐藏且无共享控制台的进程组收不到
    `CTRL_BREAK_EVENT`。因此停止策略以「直接终止整个 Job/树」为主，仅在显式 `force:
    false` 且进程有可见控制台时才尝试 `CTRL_BREAK_EVENT` 加短暂宽限；对外只暴露
    `ok/error`，不暴露信号细节。
- 任务退出码约定（0 成功 / 130 取消 / 其他失败）保留不变；退出监视线程逻辑同 mac。

### PATH 注入

- `build_launch_env` 的 Windows 版优先注入：
  - `%APPDATA%\npm`、`%USERPROFILE%\.volta\bin`、`%USERPROFILE%\.bun\bin`、
    `C:\Program Files\nodejs\`、
  - `%ChocolateyInstall%\bin`、`%ProgramFiles%`、`%SystemRoot%\System32`、`%SystemRoot%`、
    用户 PATH 原值去重。
- 后台启动（pythonw/no-console）不会读取用户 shell 配置的问题在 Windows 同样存在，
  注入逻辑即为对策（与 mac 同理）。

### 原生对话框与通知（osascript 替代）

- `POST /api/pick`（选目录/脚本）：
  - 主路径：`powershell -NoProfile -STA -Command` 调 `System.Windows.Forms.FolderBrowserDialog`
    / `OpenFileDialog`，返回绝对路径；取消返回 `{ok, canceled:true}`。
  - 回退：前端以 `<input type="file" webkitdirectory>` / `<input type="file">` 的浏览器
    原生选择上传临时路径，二次确认。
- 任务完成通知：
  - `powershell -NoProfile -Command (New-Object -ComObject WScript.Shell).Popup(...)`。
  - 失败静默降级为不通知；不阻断功能。质量低于 mac 通知中心，文档注明。

### 服务自身停止/重启

- `POST /api/console/stop` / `restart` 语义不变：响应先返回再由守护/helper 进程收尾。
  Windows 下 restart 用 `CREATE_NEW_PROCESS_GROUP` + 独立 helper 进程等待旧进程退出
  后以原端口重启；停止后 HTTP 服务关闭，启动台内已运行的独立进程组保持运行（同样以
  cmd 锚点树识别）。

## 前端改动（最小集）

- 快捷键 ⌘K/⌘J/⌘L → Windows 平台用 Ctrl+K/Ctrl+J/Ctrl+L（运行时按平台检测 modifier）。
- 文案：把「ps/lsof」「macOS」「终端」等 macOS 术语改为平台无关表述（错误信息、降级原因等）。
- 其余 UI、主题、日志中心、命令面板、端口发现、启动台全部原样。

## 测试与验收

- 移植 `tests/`（大多 mock 系统调用；适配 `kill`、`stop_pid_tree`、`lsof_cwds`、
  `scan_listeners`、`pick_path` 等签名不变仅实现换引擎）。
- 新增 Windows 端到端冒烟测试：启动/停止一个 `python -m http.server` 服务、任务退出
  码记录、端口发现、配置持久化。
- `make check` 无 make 的替代：提供 `check.ps1`（等价语法/版本/测试检查）。

## 已知取舍（必须写进文档）

1. 受保护/受限系统进程的 cwd 可能读不到 → 显示「未知（受限）」，不阻断。
2. 通知为简单弹窗，弱于 mac 通知中心。
3. 进程组语义由 Job Object + 进程树近似，等价但不能 100% 复刻 bash `wait` 等待
   后台作业的语义；批处理/服务以 `cmd /c` 同步等待为准。
4. `cpu_percent` 首帧为 0.0 的窗口期误差，随后轮询即准确。

## 验收标准

- `python server.py` 在 Windows 上启动，浏览器打开 `http://127.0.0.1:<port>/`。
- 启动台能添加一个本地服务（如 `python -m http.server 8080`）并启动/停止/重启、看日志。
- 服务监控能列出监听端口、显示启动者徽标、发现新端口并加入启动台。
- 批处理任务退出码约定生效；快捷键 Ctrl+K/J 可用。
- `check.ps1` 通过（含新增冒烟测试）。
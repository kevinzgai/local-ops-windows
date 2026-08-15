# 总控台

**Preview / Alpha · 源码预览 · Windows 变体**

本仓库是总控台的 **Windows 原生变体**。 macOS 原版请参见 `laogou717/local-ops` 仓库。Windows 适配采用 psutil 作为唯一第三方依赖，把后端从 mac 的 `lsof`/`ps`/`osascript` 改为 Windows 等价物（psutil/PowerShell/job object），保留 API 契约与前端零依赖。

> 当前版本仍处于 Preview / Alpha 阶段，以源码预览形式提供。接口、配置格式和安装方式仍可能调整；本仓库的 `start.bat` / `start-hidden.vbs` 不是自包含应用分发包，也尚不代表经过签名公证的最终 Windows 发行版。

总控台只服务当前 Windows 和当前用户，不是远程运维、多人协作或公网管理面板。它能够以当前用户权限执行保存的命令；不要将监听地址、反向代理、SSH 隧道或端口映射暴露到不受信任的网络。

## 功能

- 每 2 秒查看当前用户的本地监听服务、CPU、内存和运行时长。
- 保存常用服务或批处理任务，集中启动、停止、重启、查日志和诊断。
- 在当前页面会话中发现新出现的、尚未管理的监听端口，可直接加入启动台或忽略隐藏。
- 运行前检查工作目录、脚本和运行时；明确失效时直接给出修复入口，不必先失败一次。
- 从项目文件夹识别常用启动命令，但不安装依赖、不执行项目代码。
- 通过运行 token、进程组和当前 UID 联合识别受控进程，不会因端口相同就杀死外部进程。
- Ops 指挥台单一主题：深空蓝黑/雾灰双色，左侧导航轨、KPI 概览卡、实时动态侧栏，浅色、深色和跟随系统。
- 全局命令面板可直接添加服务或批处理任务；启动台卡片支持鼠标拖拽和键盘排序。

## 界面预览

以下截图使用脱敏演示数据，不包含真实用户名、目录、命令或服务信息。

| 启动台 | 服务监控 |
| --- | --- |
| ![Ops 指挥台 · 启动台](docs/screenshots/ops-launchpad.jpg) | ![Ops 指挥台 · 服务监控](docs/screenshots/ops-services.jpg) |

## 系统要求

- Windows 10/11
- Python 3.12（推荐从 `python.org` 下载 `Windows installer (64-bit)`，勾选 `Add python.exe to PATH`）
- `pip install psutil`（本移植唯一第三方依赖）
- Edge、Chrome 或其他支持 ES Modules 的现代浏览器

`VERSION` 是项目版本的唯一权威来源。

## 安装

1. **下载并解压**：将发行 zip 解压到一个你有读写权限的位置（如 `桌面` 或 `D:\Apps`），保持目录结构完整。
2. **安装 psutil**：在解压目录打开「终端」或「PowerShell」，执行：

   ```powershell
   pip install psutil
   ```
3. **启动**：双击 `start.bat`（前台看日志）或 `start-hidden.vbs`（无控制台窗口后台运行）。

## 运行

启动总控台有三种方式，效果相同，按习惯选择：

| 方式 | 操作 | 适用场景 |
| --- | --- | --- |
| 桌面端 exe | 双击 `dist/总控台.exe`（需先 `python tools/build_exe.py` 打包） | 免装 Python，带系统托盘（`--tray`） |
| 双击静默启动 | 双击 `start-hidden.vbs` | 日常使用。通过 `pythonw.exe` 启动，无控制台窗口 |
| 双击前台启动 | 双击 `start.bat` | 想在终端窗口看实时输出 |
| 命令行 | `python server.py` | 调试、脚本化或远程 SSH 启动 |

命令行还有两个可选参数：

```powershell
python server.py --no-browser        # 只启动服务，不自动打开浏览器
python server.py --preferred-port 9603  # 在 9600-9609 内指定优先端口
```

启动后程序只绑定 `127.0.0.1`，从 9600 起尝试端口，被占用则递增（最多 10 个），并自动打开浏览器。命令行参数、环境变量（`CONSOLE_DATA_DIR` / `CONSOLE_LOG_DIR`）见下文“数据与日志位置”。

**实际地址在哪里看**：顶栏「重启 :9600」按钮上直接显示当前端口；或看终端 / `%LOCALAPPDATA%\总控台\logs\console.log` 输出。浏览器手动访问 `http://127.0.0.1:端口号/` 即可。

**停止与重启**：顶栏「重启 / 停止」控制的是总控台自身（网页服务）。停止总控台**不会**停止启动台里已经运行的应用——它们是独立进程组（Job Object / 进程树），会继续运行；下次打开总控台时会自动重新识别。重启总控台会加载磁盘上的最新代码，同样不影响运行中的应用。

## 使用

打开页面后，左侧是导航轨，右侧是信息栏；所有数据每 2 秒自动刷新。

### 启动台（管理你的服务与任务）

- **添加服务/任务**：点「+ 添加服务」卡片或页头快捷按钮。选择工作区文件夹后会自动识别项目类型（Node/pnpm、Hexo/Hugo、Django/FastAPI、Go、Rust、静态站点等）并给出候选命令；也可以「选择脚本」或完全手动填写。`service` 是长期服务（带端口语义），`task` 是有明确结束时间的批处理（强制无端口）。
- **卡片**：大按钮启动/停止（任务是运行/中止）；右侧一排小按钮（复制链接/日志/诊断/重启/编辑/删除）常显，不用悬浮。运行中显示端口与时长；配置失效（目录/脚本丢失）会直接标出原因并禁用启动，点开「启动诊断」有修复建议。
- **筛选**：每个分区右上角可按 全部/运行中/已停止/异常（任务为 全部/运行中/成功/失败/已取消）过滤，点按即时切换。
- **排序**：鼠标拖拽，或聚焦卡片后按空格进入键盘排序（方向键移动，空格确认）。
- **批量停止**：右侧「快捷操作」里可一键停止全部运行中的应用（有确认框，逐个安全停止，绝不按端口杀进程）。

### 服务监控（看这台 Windows 在跑什么）

- **概览卡**：在线服务/后台应用/总 CPU/总内存（带最近一分钟负载曲线）/端口警告/最后更新。
- **服务表格**：每个服务的 PID、端口、目录、负载、时长、状态，以及**启动者徽标**——溯源显示这个进程是哪个 AI 助手（Codex/Claude/Kimi 等）、编辑器（VS Code/Cursor 等）、终端或总控台启动的。点端口直接打开服务；行尾按钮可加入启动台、置顶、隐藏、展开完整命令或安全结束进程。
- **发现新端口**：页面打开期间新出现的监听端口会单独提醒，可一键「加入启动台」（自动识别项目并原子认领进程）、「忽略并隐藏」或「暂时关闭」。
- **后台与已隐藏**：系统/GUI 应用进程默认折叠在「应用后台」；被隐藏的服务可随时恢复。
- **关注的进程**：输入关键字（如 `ffmpeg`）回车，匹配进程实时列出。

### 日志中心（Ctrl+J）

导航轨「日志中心」或快捷键 `Ctrl+J`（`Ctrl+L` 是浏览器保留键）：所有应用按运行中优先排列，点开任意一行看实时日志；底部固定总控台自身日志入口。

### 设置中心

导航轨齿轮：任务完成通知开关（浏览器 Web Notification + 桌面版托盘气泡，切走页面也能收到）、开机自启开关（写入当前用户注册表 Run 键）、外观三态（自动/浅色/深色）、版本/端口/工作目录/数据目录信息。

### 命令面板（Ctrl+K）

全局搜索并执行：添加服务/任务、启动/停止/重启任意应用、打开页面、查看日志、切换视图、开关任务通知、查看总控台日志等，全键盘操作。

### 使用要点

- 红色按钮会结束进程或删除应用，需要二次确认。
- 批处理任务自然退出 `0` 表示成功，其他非零退出码表示失败；脚本内部用户主动取消请退出 `130`（显示为「已取消」）；总控台按钮主动中止单独显示为「已中止」。
- 选择批处理脚本时，总控台只保存脚本的绝对路径和生成的执行命令，不会复制或托管脚本内容。脚本移动、改名或删除后，任务会失效；建议将个人脚本放在长期稳定、会单独备份的自动化目录中。
- 停止总控台不会自动停止已启动的独立服务；配置里的应用、图标、关注关键字和隐藏/置顶标记都会保留。

### 批处理退出码约定

任务自然退出 `0` = 成功，其他非零 = 失败；脚本内部用户主动取消请退出 `130`（显示为「已取消」而非失败）；总控台按钮中止显示为「已中止」。Python 用 `raise SystemExit(130)`，Shell 用 `exit 130`，Node.js 设 `process.exitCode = 130`。此约定只用于 `task`，长期服务仍按普通退出处理。

### 新端口发现的基线规则

「服务监控」只提醒**页面打开后新出现**、尚未纳入启动台的本地服务。首次载入、页面从后台恢复、断线重连或总控台重启后的第一份状态只用于建立静默基线，不会把已有端口全部弹一遍。「忽略并隐藏」写入配置并可恢复；「暂时关闭」只影响当前页面会话。

## 数据与日志位置

运行数据与程序目录分离，默认放在 Windows 用户目录：

| 路径 | 内容 | 备份建议 |
| --- | --- | --- |
| `%APPDATA%\总控台\config.json` | 应用命令、本地路径、端口、标记和运行识别信息 | 必须 |
| `%APPDATA%\总控台\config.json.bak` | 上一份已知良好的配置 | 必须 |
| `%APPDATA%\总控台\icons\` | 用户上传的图标和站点图标 | 按需 |
| `%LOCALAPPDATA%\总控台\logs\` | 应用与总控台运行日志 | 通常不需 |

可用 `CONSOLE_DATA_DIR` / `CONSOLE_LOG_DIR` 环境变量覆盖，规则与 mac 版一致（绝对路径、非符号链接、不可为根目录）。

这些文件仍可能含个人路径、完整命令和日志内容；不应进入 Git，也不应随发行包或故障报告对外传播。

### 旧版数据首次迁移

如果新目标目录尚不存在，首次启动会将项目内旧 `data/config.json{,.bak}` 和 `data/icons/` 安全复制到 `%APPDATA%\总控台\`，将 `data/logs/` 复制到 `%LOCALAPPDATA%\总控台\logs\`。迁移使用临时目录后原子落位，并且：

- 旧 `data/` 始终保留，不会自动删除。
- 目标已存在时绝不覆盖或合并，避免把更新的用户数据换回旧版。
- 符号链接和非普通文件不会被复制。
- 显式设置 `CONSOLE_DATA_DIR` 或 `CONSOLE_LOG_DIR` 时，对应目录不执行旧数据自动迁移。

需要自定义路径时：

```powershell
$env:CONSOLE_DATA_DIR = "D:\console-data"
$env:CONSOLE_LOG_DIR = "D:\console-logs"
python server.py
```

自定义值必须是非空的绝对路径，并指向总控台专用的非符号链接子目录；不要直接填盘符根目录、用户主目录或项目根目录。

### 备份

1. 不再执行新的启动、停止或编辑操作。
2. 停止总控台。
3. 将 `%APPDATA%\总控台\` 复制到受保护的备份目录。
4. 记录当前 `VERSION`，以便恢复时匹配配置格式。

### 恢复

1. 确保总控台已停止，并另存当前 `%APPDATA%\总控台\`。
2. 将备份中的 `config.json` 和 `icons\` 复制回对应位置。
3. 重新启动，逐项确认命令、工作目录和端口。

如果主配置损坏，程序会验证 `config.json.bak` 并恢复主文件。如果两份都不可用，服务进入只读保护状态，不会用空配置覆盖它们。`config.json.bak` 保留的是每次修改之前的上一份良好配置，而不是主文件的同内容副本。

## 已知取舍

本仓库是 macOS 原版的 Windows 适配，已知与原版的取舍如下：

- **受保护系统进程的 cwd 读取**：受保护系统进程对 psutil `cwd()` 报 `AccessDenied` 时显示「未知（受限）」，不阻断服务监控。
- **通知弱于 mac 通知中心**：本移植不再调用 `osascript`/`terminal-notifier`；任务完成通知为浏览器 Web Notification API（需打开过一次页面授予权限）+ 桌面版（`--tray` / exe）的服务端托盘气泡双通道，不起系统通知中心弹窗。
- **受控进程组语义**：mac 版借助 shell 进程组 + `wait` 等待后台作业；Windows 上以 `cmd.exe` 锚点 + Job Object 收紧，再以 psutil 进程树作进程组成员判定，等价于但不复刻 bash `wait` 等待后台作业的语义；批处理/服务以 `cmd /c` 同步等待为准。
- **温和停止不可靠（放弃 GenerateConsoleCtrlEvent 方案）**：`GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT)` 只能发给与调用方共享控制台的进程，而受控进程组以 `CREATE_NO_WINDOW` 隐藏启动、`pythonw` 无控制台，无法可靠共享控制台；停止策略以「Job Object 终止 / taskkill /T /F 进程树」为主，没有真正的渐进式温和停止。
- **桌面端为便携 exe + 系统托盘，无安装包/签名/自动更新**：`tools/build_exe.py` 产出单文件 `dist/总控台.exe`（`--tray` 启用托盘，右键「打开面板/停止/退出」、双击打开面板），免装 Python；但当前不做安装包、代码签名与自动更新，未签名的 onefile exe 可能触发 SmartScreen / 杀软误报。源码模式（`start.bat` / `start-hidden.vbs` / `python server.py`）完整保留，不受影响。
- **PATH 探测**：Windows 启动不读取 shell 配置；启动环境由平台层显式补入常用 `Scripts / AppData / Program Files` 路径与 `PATHEXT` 关联后缀，命令自动补 `.exe / .cmd / .bat`，不靠 `lsof`/`ps`/`osascript` 等只在 mac 上存在的工具。

## 升级

1. 阅读 `CHANGELOG.md`，确认是否有配置或平台变更。
2. 停止总控台并完整备份 `%APPDATA%\总控台\`。
3. 用新版本替换程序文件；用户数据保持在 `%APPDATA%` / `%LOCALAPPDATA%` 中。
4. 运行 `powershell -ExecutionPolicy Bypass -File tools/run_tests.ps1`。
5. 启动后检查应用数量、主题、关注关键字和一个可控服务的完整启停。

配置包含 `schemaVersion`，启动时逐版执行显式、幂等迁移。新程序不会静默降级它不认识的更高 schema；回退程序时仍应同时恢复与该版本匹配的数据备份。

## 卸载

1. 如果不希望已启动的服务继续运行，先在启动台逐个停止它们。
2. 停止总控台。
3. 按需导出 `%APPDATA%\总控台\` 备份。
4. 将整个项目目录从文件管理器移到回收站。
5. 确认不再需要数据后，手动删除 `%APPDATA%\总控台\` 和 `%LOCALAPPDATA%\总控台\`。

程序不会安装系统启动项，卸载时也不会自动删除用户数据。

## 安全边界

总控台不是多用户服务器或远程管理面板。它能以当前 Windows 用户的权限执行你保存的命令，因此：

- 只添加你已检查且信任的命令和工作目录。
- 不要将服务绑定到 `0.0.0.0`，不要通过反向代理、SSH 隧道或端口映射对外暴露。
- 不要在共享或不受信任的用户账户中运行。
- 不要把 `%APPDATA%\总控台\config.json`、日志或故障截图未经脱敏就上传。
- 本地回环绑定只是第一层边界，不能替代写接口的 Host/Origin/控制令牌防护。发布验收时必须执行 `RELEASE_CHECKLIST.md` 中的安全项。

## 故障排查

### 双击后没有界面

- 确认 `python --version` 可用且符合要求 3.12 或更高。
- 查看 `%LOCALAPPDATA%\总控台\logs\console.log`。
- 用 `python server.py` 从终端启动，直接查看错误。
- `start-hidden.vbs` 启动后无窗口，无法直接观察日志；调试时改用 `start.bat`。
- 不要把 `start.bat` / `start-hidden.vbs` 单独拷走；它们依赖同目录的 `server.py` / `platform_win.py` / `static/`。

### `python not found`

- 先确认 `python --version` 在 PATH 里能调用；如未生效，重新安装 Python 时勾选「Add python.exe to PATH」。
- 若 PATH 里有多个 `python`，优先用 `python`（来自 `python.org` 安装器），避免 `WindowsApps\python.exe` 这个 MS-Store 占位 shim。
- 完全找不到 Python 时，用 `py -3 -m pip install psutil` 替代 `pip install psutil`，`py` 启动器来自官方安装包。

### 9600 打不开

- 程序可能已选择 9601–9609。查看终端输出或 `%LOCALAPPDATA%\总控台\logs\console.log` 中的实际地址。
- 服务可访问时，`GET /api/health` 会返回程序版本、配置 schema 和降级原因，且不会执行 psutil 全表扫描。
- 端口被其他程序占用并不会主动结束；总控台只在 9600–9609 内自动 +1 找空位。
- `start-hidden.vbs` 启动后台后看不到窗口；用 `tasklist /FI "IMAGENAME eq pythonw.exe"` 确认进程仍在，再用 `curl http://127.0.0.1:<port>/api/health` 验证。

### 应用启动失败

- 先打开该应用的日志和「启动诊断」。
- 确认工作目录仍然存在、命令可在普通 PowerShell / CMD 中独立运行。
- 检查启动瞬间配置端口是否正被其他进程占用；不同项目允许保存相同的常见开发端口。
- 双击 / VBS 启动的应用不会读取你的 PowerShell profile；总控台会补入常用 `Scripts / AppData / Program Files` 路径、`PATHEXT` 关联后缀，但非标准安装位置仍需显式绝对路径。
- 受保护进程的工作目录会显示「未知（受限）」，属已知取舍，不影响启停判定。

### 配置丢失或损坏

停止总控台，保留当前 `config.json`，然后按上文「恢复」流程使用已知良好的 `config.json.bak` 或离线备份。

### PowerShell 弹窗（选目录 / 选脚本）没出现

- 默认通过 `powershell -STA -NoProfile -ExecutionPolicy Bypass -Command` 调用 WinForms 对话框；首次执行可能被 SmartScreen 拦截，点「仍要运行」即可。
- 在受限/服务器核心环境没有 WinForms 时，对应 `POST /api/pick` 会返回错误，可改用「手动输入路径」。

### 受控进程无法停止

- Job Object 终止与 `taskkill /T /F /PID` 是双重兜底：先 `TerminateJobObject` 终止 Job 内全部进程，失败则走 `taskkill /T /F` 进程树。
- 在「快捷操作 → 停止全部」中只停止总控台受控进程，绝不按端口杀其他监听者；外部服务请用手工结束进程或服务自带控制面板。

## 开发

运行时唯一第三方依赖是 `psutil`（数据面采集）。开发与重新生成图标不需要额外依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install psutil
```

主要目录：

```text
server.py                 Python 后端（HTTP/配置/前端路由）
platform_win.py           Windows 平台适配层（psutil + Job Object + 进程树 + cmd 锚点）
static/                   原生前端、主题、品牌、图标和字体
tests/                    后端、前端契约、发布与交付检查
tools/                    check_project / run_tests / gen_icons / gen_brand_assets
data/                     旧版运行数据（仅首次迁移源，不进 Git/发行包）
```

### 检查

提交前的权威命令是：

```powershell
powershell -ExecutionPolicy Bypass -File tools/run_tests.ps1
```

它会检查 Python/JavaScript/JSON 语法、版本一致性、主题和资源引用、生成的图标是否同步，并显式发现和运行测试。测试数量为 0 时会失败，不会出现「0 tests 也算通过」。等价命令 `make check`（Windows 下走 PowerShell）也可用。

只运行后端测试：

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

正式发布前还应运行 `make release-check`（同样走 `tools/run_tests.ps1`），它会额外检查 Git 状态和不应进入发行范围的文件；不会代替 `RELEASE_CHECKLIST.md` 中的人工验收。

### 重新生成资源

```powershell
make generate-icons
make generate-brand
make check
```

`static/icons.js` 是生成文件，不应手工修改。`generate-brand` 以 `static/assets/console-app-icon.png` 为主源，需要 PowerShell 调用 `System.Drawing` 输出 `favicon-32.png` / `favicon.ico` / `apple-touch-icon.png`；本移植不再生成 macOS `AppIcon.icns`。重新生成品牌图标后，只提交预期的差异，并同步更新 `ASSET_PROVENANCE.md` 的 SHA-256。

## 发布

请按 `RELEASE_CHECKLIST.md` 逐项验收。一个可对外交付的版本至少需要：

- 与根目录 MIT 许可证一致的版权信息，以及全部第三方素材和项目图像的来源、许可与授权凭证。
- 干净、可追溯的 Git commit 和带签名版本 Tag。
- 通过 `make release-check` 和人工 UI/安全/升级/回滚验收。
- 不含任何项目内旧 `data/`、用户 `%APPDATA%` / `%LOCALAPPDATA%` 数据、日志、绝对路径、token 或缓存的发行包。
- 针对目标 Windows 的完整性校验、全新安装和回退证据（macOS 签名 / 公证不适用本变体）。

## 参与贡献与安全

- 提交代码前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)，并运行 `make check`。
- 行为规范见 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。
- 安全问题不要作为普通公开 Issue 披露；报告方式和脱敏要求见 [`SECURITY.md`](SECURITY.md)。
- 新增或替换字体、图标、插画、纹理等素材时，必须同步更新 [`ASSET_PROVENANCE.md`](ASSET_PROVENANCE.md) 和 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 许可与第三方素材

项目自有代码和文档采用 [`MIT License`](LICENSE)。Lucide、Geist Mono 以及项目生成图像等素材可能适用各自的许可或发布限制，不因根目录 MIT 许可证而自动改变，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 与 [`ASSET_PROVENANCE.md`](ASSET_PROVENANCE.md)。

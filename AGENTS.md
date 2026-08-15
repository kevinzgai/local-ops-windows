# 总控台 (Console)

**Windows 变体**

本地服务监控与快速启动控制台。**唯一第三方依赖** `psutil`：Python 3.12 后端 + 配套 Windows 平台适配层 + 无构建原生前端。推荐双击 `start-hidden.vbs` 后台运行（无控制台窗口）；`start.bat` 保留为终端调试入口。

> 本仓库是 macOS 原版的 **Windows 原生变体**。macOS 原版请参见 `laogou717/local-ops`。Windows 适配把后端从 `lsof`/`ps`/`osascript` 改为 psutil/PowerShell/Job Object，**保留 API 契约与前端零依赖**。所有 macOS 行为细节（`laogou717/local-ops`）保留并行维护。

## 结构

- `server.py` — 后端（HTTP/配置/前端路由，Python 3.12）
- `platform_win.py` — **Windows 平台适配层**（psutil 数据面 + Job Object + 进程树 + PowerShell 对话框 + cmd 锚点；函数签名与 `platform_darwin.py` 一一对应，`server.py` 的 import 在 Windows 上指向这里）
- `static/index.html` / `static/app.js`（入口）/ `static/js/{core,launchpad,services,overlays,ports,widgets}.js`（原生 ES Modules，无构建）/ `static/icons.js` — 前端（原生，禁框架/CDN/构建）；`core.js` 承载工具/API/浮层/状态/主题注册，`launchpad.js` 卡片+拖拽+诊断+启动台 KPI/分区过滤，`services.js` 表格+监控 KPI 火花线，`overlays.js` 模态+抽屉，`ports.js` 端口归一化纯函数，`widgets.js` 右侧信息栏（实时动态/告警、TOP5、小贴士、快捷操作）与导航轨状态；模块间用 `window.__poll` 共享轮询入口
- 布局 v2：左侧 `.rail` 图标导航轨（启动台/服务监控视图切换 + 日志中心/设置中心弹层入口）+ 顶栏 + 内容/右侧信息栏双栏网格（≤1280px 侧栏下沉到底部、≤900px 导航轨隐藏）；结构样式集中在 `static/base.css` 末尾「布局 v2」段（主题令牌驱动），主题包负责视觉皮肤
- `static/themes/` — **单一主题**：当前仅内置 `ops`（指挥台，`DEFAULT_UI_THEME` 常量指定并在清单中固定排首位）。`{id}.css` 整包样式 + `{id}.json` 清单（`id/name/author/desc/colors[]`）的注册机制保留：`GET /api/state` 返回 `themes` 与 `uiTheme`；`POST /api/ui/theme {theme}` 校验 id 后落盘。产品不提供主题选择界面（已随多主题一并移除），深浅色切换仍保留。
- `static/fonts/GeistMono-Variable.woff2` — vendored 数据/代码字体；中文与正文使用 Windows 系统字体栈（`Segoe UI` / `Microsoft YaHei` 等）；`static/icons/*.svg` — Lucide 图标源文件（vendored）；`tools/gen_icons.py` — 由 svg 重新生成 `icons.js`（勿手改 icons.js）
- `static/assets/` — 品牌素材：`console-app-icon.png` 为 App Icon 主图，`brand-mark.png` 为顶栏标识；`favicon-32.png` / `favicon.ico` / `apple-touch-icon.png` 由 `tools/gen_brand_assets.py` 生成（不再生成 `AppIcon.icns`）
- `%APPDATA%\总控台\config.json` — 用户配置；`icons/` 为应用图标。Windows 不支持 POSIX 0o700/0o600 模式位，目录与文件按 NTFS DACL 收紧为当前用户可读写
- `%LOCALAPPDATA%\总控台\logs\{appId}.log` — 应用启动日志；`console.log` 为 `start.bat` / `start-hidden.vbs` 启动日志
- `data/` — 旧版项目内数据，仅在新目标不存在的首次启动中复制迁移；保留不删除
- `start.bat` — Windows 双击启动入口（前台运行；`chcp 65001` + `python server.py %*`）。**保持 ANSI/GBK 编码**：cmd 按当前代码页逐行读取批处理，转 UTF-8 会在默认 GBK 代码页下中文乱码（含中文菜单，勿改）
- `start-hidden.vbs` — 后台静默启动（通过 `pythonw.exe` 启动，无控制台窗口；等价于 mac 版 `总控台.app` 的 `LSUIElement` 后台用法）；含中文注释的 `.ps1` 一律保存为 **UTF-8 with BOM**（PowerShell 5.1 对无 BOM 文件按 ANSI 解码，注释会乱码）

## 运行

`python server.py` → 绑定 `127.0.0.1`，端口从 **9600** 起尝试，被占则 +1（最多 10 个）。启动后自动打开浏览器。`/favicon.ico` 返回统一品牌图标。双击 `start-hidden.vbs` 通过 `pythonw.exe` 启动后台实例（无控制台窗口）；`start.bat` 以前台方式运行（便于查看实时日志）。

## API 契约（全部 JSON；icon 上传为原始字节）

### `GET /api/state` — 前端唯一轮询接口
```json
{
  "services": [{
    "key": "python3.12:8791", "instanceKey": "54252:8791",
    "pid": 54252, "name": "python3.12", "port": 8791,
    "cwd": "/Users/example/xx项目", "project": "xx项目", "cmd": "python3 app.py",
    "cpu": 0.3, "mem": 1.2, "uptimeSec": 7980,
    "group": "mine", "pinned": false, "hidden": false, "promoted": false,
    "appId": null, "appName": null,
    "origin": {"label": "Codex", "icon": "bot"}
  }],
  "watched": [{"pid": 1, "name": "ffmpeg", "cmd": "...", "cpu": 0.0, "mem": 0.5, "uptimeSec": 60, "keyword": "ffmpeg"}],
  "apps": [{
    "id": "a1b2c3d4", "name": "我的博客", "command": "python3 -m http.server 8080",
    "cwd": "/path", "port": 8080, "emoji": "🚀", "glyph": "rocket", "icon": "/icons/a1b2c3d4.png",
    "kind": "service", "attached": false,
    "running": true, "pid": 1234, "uptimeSec": 120,
    "listening": true, "portOccupied": false, "portOccupiedPid": null,
    "portConflict": false, "portConflictApps": [],
    "lastExit": {"status": "succeeded", "code": 0, "at": 1700000000, "startedAt": 1699999998750, "durationSec": 1.25},
    "health": {"status": "ok", "blocking": false, "issues": []},
    "favicon": "/icons/fav-a1b2c3d4.png",
    "ports": [8080],
    "listening": true, "portOccupied": false, "portOccupiedPid": null,
    "portOwner": null, "portConflict": false, "portConflictApps": []
  }],
  "watchedKeywords": ["ffmpeg"],
  "taskNotifications": false, "autostart": false,
  "consolePort": 9600, "consolePid": 123, "consoleCwd": "/path/to/总控台",
  "version": "1.0.0", "schemaVersion": 1,
  "degraded": false, "degradedReasons": []
}
```
- `GET /api/health` — 不做 psutil 全表扫描的轻量健康检查，返回 `status/version/schemaVersion/degraded/issues/config`
- `group`: `"mine"` | `"background"`；`icon`/`emoji`/`port`/`cwd`/`project`/`appId`/`appName`/`lastExit` 可为 `null`
- `lastExit`：最近一次退出结果。任务状态为 `succeeded`（exit 0）/`canceled`（脚本主动 exit 130）/`failed`（其他自然退出）/`stopped`（总控台中止，code=null）；旧数据可能只有 `code/at`，API 输出时会兼容推导但不改写磁盘。批处理启动时保留上一次完成历史，自然退出或中止后覆盖
- `health`：每次状态读取时只读检查配置，返回 `status: ok|error|unknown`、`blocking` 与 `issues[{kind,severity,title,detail,fix,action}]`。明确缺失的 cwd、脚本或运行时会阻止启动；复杂命令（cmd / PowerShell / bash 拼接、变量展开、管道等）无法静态判断时为 unknown，不阻止运行
- `kind`：`"service"`（长期服务，有端口语义）| `"task"`（批处理任务，强制 port=null，主按钮为「运行」）；旧数据缺省视为 `service`。启动台按 kind 分两个区渲染
- `running`：仅表示存在通过本次启动 token、进程组与当前用户三重校验的受控进程；不再以“配置端口有任意监听者”作为运行依据
- `attached`：用户从服务监控明确认领的外部服务身份。此类服务的监听子进程换 PID 后，可按配置端口 + 当前 UID + 真实 cwd 唯一重新关联；普通卡片仍不得仅凭端口自动认领
- 服务行的 `key` 保持 `name:port` 以兼容隐藏/置顶配置；`instanceKey` 使用 `pid:port` 区分同名同端口后来出现的新进程实例，前端发现与 DOM 对账均使用它
- `listening`：受控进程是否正在监听配置端口；`portOccupied`：该端口当前被不属于本卡片的进程占用；多张卡片允许保存同一个常见开发端口，`portConflict/portConflictApps` 仅为旧前端兼容字段并固定返回 `false/[]`；`legacyManaged`：是否通过旧版 PID+端口+UID+cwd 兼容身份识别
- `project`：cwd 最后一段目录名（用于区分同名进程）；`appId`/`appName`：该端口命中启动台应用时的关联信息
- 排除控制台自身进程；只返回当前用户的进程
- **进程溯源**：`origin` 沿 PPID 链（≤12 层）识别启动者——跳过壳/包管理器/运行时包装层，优先匹配已知 AI 编程助手（codex/claude/kimi/gemini/aider/opencode 等）、编辑器/终端进程（`code.exe` / `cursor.exe` / `WindowsTerminal.exe` / `cmd.exe` / `powershell.exe` 等）、Windows Terminal 与总控台 run-token 标记（「总控台」）；未识别的中间层先记为候选、有更优答案即覆盖，全部落空才以最近未识别进程命名；`label` 为展示名、`icon` 取 bot/code/terminal/package/rocket/server，仅用于展示，不影响启停判定

### 服务操作
- `POST /api/kill` `{pid, force?}` → `{ok}` / `{ok:false, error}`（force=True 走 `proc.kill()`/`TerminateProcess`，否则 `proc.terminate()`；Windows 两者均调用 `TerminateProcess`，仅保留分层语义；校验属当前用户）
- `POST /api/services/flag` `{key, flag: "hidden"|"pinned"|"promoted", value: bool}` → `{ok}`（promoted=false 即「移回后台」，前端对 `svc.promoted` 的行显示该按钮）
- `POST /api/watch` `{keyword, action: "add"|"remove"}` → `{ok, keywords}`

### 启动台应用
- `POST /api/apps` `{name, command, cwd?, port?, emoji?, glyph?, kind?, attachPid?}` → app 对象（`kind` 缺省 `service`；`task` 强制 port=null；服务监控来源可带 `attachPid`，后端先校验 PID/端口/UID/cwd，再将卡片与运行身份一次写入，失败不创建半成品卡片）
- `POST /api/pick` `{what: "dir"|"script"}` → `{ok, path}` / `{ok, canceled:true}`（PowerShell `-STA` 调用 WinForms `FolderBrowserDialog` / `OpenFileDialog`；取消不是错误）
- `POST /api/project/detect` `{cwd}` → `{ok, cwd, name, files, candidates:[{command,label,source,port,kind,detail}]}`（只读分析项目根目录，不执行项目代码；识别 package.json scripts 与包管理器锁文件、Hexo/Hugo/Jekyll、Django/FastAPI/Flask/Streamlit、Docker Compose、Go、Rust、常用启动脚本及纯静态站点。Hexo 无 scripts 时仍返回 `hexo s` 服务与 `hexo cl` 任务）
- `POST /api/apps/reorder` `{ids: [...]}` → `{ok}`（按 ids 重排 apps 数组；Python sort 稳定，未涉及的 id 相对顺序不变，服务/任务两区可独立拖拽排序互不干扰）
- `PUT /api/apps/{id}`（部分更新同字段，可带 `stopBeforeUpdate:true`）→ app 对象；运行中修改 command/cwd/port/kind 时，缺少该标记返回 `{ok:false, requiresStop:true}`，带标记则安全停止后原子保存
- `DELETE /api/apps/{id}` → `{ok}`（先停止再删，连同图标/日志）
- `POST /api/apps/{id}/start` → `{ok, pid}` / `{ok:false, error, health?}`（已运行则报错；启动前复查配置健康，明确失效返回 422；批处理启动后立即返回，由退出监视线程记录结果，快速成功任务不会被误判成启动失败）
- `POST /api/apps/{id}/stop` → `{ok}` / `{ok:false, error}`
- `POST /api/apps/{id}/restart` → `{ok, pid}` / `{ok:false, error}`（仅重启 token 校验通过的受管进程；等待旧进程退出后再启动，不自动 SIGKILL）
- `POST /api/apps/{id}/diagnose` → `{ok, issues:[{kind,title,detail,fix,action?}], summary}`（本地规则诊断，不调外部 AI：合并运行前健康检查，并覆盖依赖未装/模块缺失、npm 脚本名错误、运行时端口占用、权限不足、pip 包缺失与退出码兜底判读；前端在配置失效或运行失败时显示诊断入口）
- `POST /api/apps/{id}/attach` `{pid}` → `{ok, pid, cwdUpdated?, cwd?}` / `{ok:false, error}`（把已在监听配置端口的当前用户进程**认领**为本卡片受管进程：走 legacy 身份通道 lastPid+端口+UID+真实 cwd 四重校验，cwd 不一致时原子同步为进程实际目录；拒绝 task、无端口、已运行、非当前用户、他卡已认领与未监听该端口的进程。前端在端口诊断弹窗提供「认领为本卡片」）
- `POST /api/apps/{id}/icon`（body 为 png/jpg/webp 原始字节）→ `{ok, icon}`
- `POST /api/apps/{id}/favicon` → `{ok, favicon}` / `{ok:false, error}`（按有效端口抓站点图标：解析首页 `<link rel*icon*>`，兜底 `/favicon.ico`，支持 png/jpg/webp/ico/svg，存入 `%APPDATA%\总控台\icons\fav-{id}.{ext}` 并写入 `app.favicon`；图标优先级：上传 icon > glyph > favicon > 名称首字，前端在无 icon/glyph 且运行中时自动触发一次）
- `DELETE /api/apps/{id}/icon` → `{ok}`
- `GET /api/apps/{id}/logs?tail=300` → `{text}`

### 总控台自身
- `POST /api/console/restart` → `{ok, pid, helperPid, port}`（先返回响应，再由独立 helper 等待旧进程退出并优先复用原端口；启动台应用不随总控台停止）
- `POST /api/console/stop` → `{ok, pid, port}`（响应发出后关闭总控台 HTTP 服务；启动台中已经运行的独立进程组保持运行）
- `POST /api/console/autostart` `{enabled}` → `{ok, enabled}` / `{ok:false, error}`（写/删当前用户 HKCU Run 键，经 `platform.set_autostart`，无需管理员；`/api/state` 的 `autostart` 反映状态且结果缓存，避免每 2s 轮询跑 reg query）
- `POST /api/console/notifications` `{enabled}` → `{ok, enabled}`（持久化 `taskNotifications`；`--tray` 模式下批处理任务自然结束时由服务端发托盘气泡通知，与浏览器 Web Notification 互补）
- `POST /api/ui/theme` `{theme}` → `{ok, theme}` / `{ok:false, error}`（校验主题 id 存在后写入 `config.json` 的 `uiTheme`；主题清单由 `/api/state` 的 `themes` 字段返回）

### 静态
`GET /` → `static/index.html`；`/app.js`、`/js/*`、`/themes/*`、`/assets/*`、`/fonts/*` 等映射 `static/`；`/icons/xxx` → `%APPDATA%\总控台\icons\xxx`。防路径穿越。

## 后端实现要点（Windows 变体）

- **端口扫描**：`psutil.net_connections(kind="tcp")` 过滤 `LISTEN`，按 `(pid, port)` 去重（同一 `(pid, port)` 多 host 时保留为集合）。
- **进程详情**：`psutil.process_iter(attrs=["pid","name","cmdline","create_time","memory_percent","cpu_percent","username"])` 批量取 `pid/comm/cmdline/create_time/memory_percent/cpu_percent/username`；`SELF_UID` 是当前用户名（`str`），不再像 mac 版那样是数字 uid。
- **cwd**：`psutil.Process(pid).cwd()`；`AccessDenied` / `psutil.AccessDenied` / 受保护系统进程静默跳过，UI 显示「未知（受限）」。
- **etime 解析**：`created_time` 直接用 `time.time() - create_time` 得到秒数，不再解析 `[[dd-]hh:]mm:ss`。
- **分组逻辑**（按优先级）：用户 `promoted` → `mine`；进程名含开发关键词（python node ollama docker 等，见 `DEV_KEYWORDS`）→ `mine`（覆盖下方规则）；PathResolver 解释出来的可执行路径含 `.app/Contents/`（macOS 兼容层）→ `background`；comm 以系统路径开头（Windows 等价路径如 `C:\Windows\System32\`、`C:\Windows\SystemApps\`）→ `background`；comm 或 cwd 含 `WindowsApps` / `Windows Defender` 沙盒路径 → `background`；其余默认 `mine`。`hidden` 仅是标记，照常返回。
- **关注进程**：同 `psutil.process_iter`，args 小写包含关键字即命中，只保留当前用户并排除自身及 psutil 探测进程。
- **应用状态**：每次启动生成随机 `runToken`，写入 `config.runToken` 并作为 `env["CONSOLE_RUN_TOKEN"]` 注入子进程环境变量。运行判定：默认走 `process_tree(lastPid)`（cmd 锚点 + 后代 psutil 树）+ 当前 UID；`attached` 卡片允许监听子进程换 PID，但必须按端口 + UID + 真实 cwd 唯一命中。Job Object 分配不参与 running 判定（只用于停止）。
- **受控进程**：本次启动生成随机 `runToken`（写入 config + 子进程环境变量 `CONSOLE_RUN_TOKEN`）；运行判定 = `process_tree(lastPid)` 锚点 + 后代树 + 同账户。
- **停止**：Job Object 优先（`CreateJobObjectW` / `AssignProcessToJobObject` / `TerminateJobObject` via ctypes），回退 `taskkill /T /F /PID <anchor>`。Job 句柄由 `take_job` 取出后所有权转移给 `terminate_job` 关闭，避免内核对象泄漏。
- **后台启动**：`cmd.exe` 作为锚点进程；`subprocess.Popen(command, shell=True, cwd=cwd, env=env, stdout=log_fd, stderr=STDOUT, stdin=DEVNULL, creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)`。`shell=True` 是必要的：list 形式经 `subprocess.list2cmdline` 转义后含 4 个引号，cmd `/s` 会剥离首尾引号破坏带内层引号的命令；`shell=True` 让 Popen 把 command 直接交给 cmd.exe，cmd 仍作为锚点（Job Object / `process_tree` 基于此 pid）。`runToken` 通过 `env["CONSOLE_RUN_TOKEN"]` 注入（不写入 cmd argv：实测在 command 前拼 `rem console-run:<token> & ` 会被 cmd /c 引号解析吞掉 `&` 后的命令，导致退出码变 0、服务不启动）。溯源走 `ppid == SELF_PID` 判定。
- **应用启停**：多张卡片可保存相同端口；启动前只拒绝失效配置和当时真实被占用的端口。重启先做健康预检，失败时不会先停掉仍工作的旧服务。停止先校验 token，然后调用 Job Object / `taskkill /T` 终止进程组，**绝不按端口杀其他监听者**。服务手动 stop 不记录退出历史；任务自然结束记录四态结果，总控台中止记录 `stopped`。批处理不做「长期服务存活探测」，避免把快速成功误判成失败。
- **任务取消协议**：同上，退出码 **130** 表示「已取消」。
- **配置健康**：`inspect_app_health` 只解析确定无歧义的简单命令并执行 `os.stat` / 权限 / PATH 检查，不执行命令、不展开变量/通配符。相对脚本按配置 cwd（空值时 `%USERPROFILE%`）解析；复杂或动态命令返回 unknown。
- **运行中编辑**：编辑面板打开时立即显示「停止服务」。点击只调用 stop，面板保持打开且当前草稿不变；停止成功后用户继续编辑并普通保存。名称/图标仍可在运行中直接保存。`stopBeforeUpdate:true` 保留为 API 客户端的原子停止更新能力。
- **无终端 PATH**：`start-hidden.vbs` / `start.bat` 不读取 PowerShell profile；启动环境由 `platform_win` 显式补入常用 `Scripts / AppData / Program Files / Program Files (x86)` 路径、`PATHEXT` 关联后缀（`.EXE / .CMD / .BAT / .PS1`），保证 `python` / `node` / `npm` 等可用。启动 API 短暂探测立即退出，并把日志末行作为明确错误返回。
- **对话框与通知**：`pick_path` 用 `powershell -NoProfile -STA -ExecutionPolicy Bypass -Command` 调用 `System.Windows.Forms.FolderBrowserDialog` / `OpenFileDialog`；任务完成通知：浏览器 Web Notification API（需先打开过页面授予权限）+ `--tray` 模式下服务端托盘气泡（`TrayIcon.notify` 走 NIF_INFO，无需浏览器）；开机自启写/删 HKCU Run 键（`set_autostart` / `get_autostart`，经 `reg.exe`）。
- **文件锁**：单实例锁用 `msvcrt.locking`（首发字节排他锁），不再用 Unix `fcntl`；解锁依赖进程退出。
- **signal 与 kill**：`signal` 模块常量在 Windows 上仍可用；`os.kill` 在 Windows 上调用 `TerminateProcess`；`platform_win.terminate_pids` 复用先子后父语义（`proc.terminate()` / `proc.kill()` 在 Windows 行为相同，均为 `TerminateProcess`）。
- **日志**：单文件超过 10MB 时 copy-truncate，保留 3 份轮转备份；日志 API 从文件尾部分块读取，不将整个日志读入内存。
- **keep-alive 陷阱**：POST start/stop 前端会带 `{}` body，handler 必须 `discard_body()` 读掉——否则残留字节污染同一 keep-alive 连接的下一个请求（method 解析成 `{}GET` → 501，前端显示断连横幅）。新增不读 body 的 POST 路由时同样处理。
- **运行目录**：默认配置/图标位于 `%APPDATA%\总控台`，日志位于 `%LOCALAPPDATA%\总控台\logs`；`CONSOLE_DATA_DIR` / `CONSOLE_LOG_DIR` 可显式覆盖，覆盖时对应目录不自动迁移旧 `data/`。Windows 不支持 POSIX 0o700/0o600 模式位，按 NTFS DACL 收紧为当前用户可读写。
- **配置**：读写加线程锁；写入用临时文件 + `os.replace` 防损坏；`schemaVersion` 逐版显式迁移；`.bak` 保留上一份良好版本。主配置与备份均不可读时进入只读保护，不覆盖原文件。
- **项目识别**：仅读取项目根目录下不超过 2MB 的已知配置/入口文件，不安装依赖、不执行配置、不扫描整个目录；显式 CLI 端口优先于框架默认端口。识别到的命令为 Windows 兼容版（`python` / `py -3` / `npm` / `pnpm` / `npx` / `go run` 等）。
- **kill 安全**：只允许结束当前用户的进程；`pid_alive` 用 `psutil.pid_exists`，`process_uid` 走 `psutil.Process(pid).username()`。

## 配置 schema
```json
{
  "schemaVersion": 1,
  "apps": [{"id": "8位hex", "name": "", "command": "", "cwd": null, "port": null, "emoji": null, "icon": null, "favicon": null, "kind": "service", "lastPid": null, "lastPgid": null, "runToken": null, "attached": false, "lastExit": null, "createdAt": 0}],
  "hidden": ["name:port"], "pinned": ["name:port"], "promoted": ["name:port"],
  "watchedKeywords": [],
  "taskNotifications": false,
  "uiTheme": "ops"
}
```

- `lastPid` / `lastPgid`：Windows 上两者并存，`lastPgid` 取值为 cmd 锚点进程的 pid（与 `lastPid` 在本变体里数值相同；保留字段为 API 兼容与跨平台代码共用）。
- `runToken`：每次启动随机生成，写入 config 与子进程环境变量 `CONSOLE_RUN_TOKEN`；运行判定要走 token，不能仅凭 pid。

## 前端要求

- 中文 UI，单页两视图（侧边导航：启动台 / 服务监控），每 2s 轮询 `/api/state`
- 添加服务时选择工作区文件夹后自动调用项目识别并展示候选命令；用户点选候选后再填入命令/端口。原有“选择脚本”与手动填写入口必须保留
- 编辑运行中服务时，表单内立即显示“停止服务”；停止操作不得关闭编辑面板或清除已经填写的内容，停止后恢复普通“保存”
- 批处理运行中显示实时耗时和「中止」入口；结束后明确显示成功/取消/失败/中止、距今时间与耗时。失败时突出日志入口；首次加载已有历史不重复提醒
- 停止状态下配置健康有阻断问题时，卡片显示第一项原因、禁用运行/启动并开放「配置与运行诊断」；运行中的停止/中止入口不得被健康问题禁用
- 服务监控只在当前页面会话连续轮询期间提醒新出现的、未管理的 mine 端口；首次加载、断线/后台/降级/重启恢复时静默建立基线。发现栏提供「加入启动台」「忽略并隐藏」「暂时关闭」
- 从服务监控或新端口发现点击「加入启动台」时，项目识别完成前不得保存；创建请求必须携带 `attachPid`，由后端原子完成卡片创建与来源 PID 认领，失败时不留下“已创建但未认领”的半成品卡片；成功后卡片直接显示运行中
- DOM 按 key 原地更新，禁整列表重绘闪烁；fetch 失败显示断连横幅
- 深浅色跟随系统 + 手动切换（localStorage `console-theme`）；**单一 UI 主题 Ops 指挥台**（ops.css：深空蓝黑/雾灰双色 + 柔和圆角细边 + 蓝色强调，配合布局 v2 的导航轨/KPI 图标卡/实时动态侧栏；`#themeCss` 整包加载机制保留）；字体 = Windows 系统字体栈（`Segoe UI` / `Microsoft YaHei` / `Cascadia Mono`）+ Geist Mono（数据/代码）；顶栏品牌图标 = `static/assets/brand-mark.png`；UI 零 emoji
- 动效：卡片入场 stagger（`--d`）、hover 浮起、模态/抽屉缓动、按键下压回弹、`prefers-reduced-motion` 降级
- 危险操作（结束进程/删除应用）必须确认

# 等价于 macOS 的 make check：
# 1) 语法/结构/生成文件检查  2) 单元测试
$ErrorActionPreference = "Stop"
$pythonCmd = $env:PY
$pythonArgs = @()
if (-not $pythonCmd) {
    foreach ($candidate in @("python", "py")) {
        $resolved = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
        if ($resolved -and ($resolved -notmatch 'WindowsApps\\python\.exe$')) {
            $pythonCmd = $resolved
            if ($candidate -eq "py") { $pythonArgs = @("-3") }
            break
        }
    }
}
if (-not $pythonCmd) {
    Write-Error "未找到 Python：请安装 Python 3.12（勾选 Add python.exe to PATH）或设置 PY 环境变量指向 python.exe"
    exit 1
}
& $pythonCmd @pythonArgs tools/check_project.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonCmd @pythonArgs -m unittest discover -s tests -p "test_*.py" -v
exit $LASTEXITCODE
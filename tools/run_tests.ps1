# 等价于 macOS 的 make check：
# 1) 语法/结构/生成文件检查  2) 单元测试
$ErrorActionPreference = "Stop"
$pythonCmd = $env:PY
if (-not $pythonCmd) {
    foreach ($candidate in @("python", "py")) {
        $resolved = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
        if ($resolved -and ($resolved -notmatch 'WindowsApps\\python\.exe$')) {
            $pythonCmd = $resolved
            break
        }
    }
}
if (-not $pythonCmd) {
    $pythonCmd = "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
}
& $pythonCmd tools/check_project.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonCmd -m unittest discover -s tests -p "test_*.py" -v
exit $LASTEXITCODE
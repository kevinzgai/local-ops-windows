# 等价于 macOS 的 make check：
# 1) 语法/结构/生成文件检查  2) 单元测试
$ErrorActionPreference = "Stop"
python tools/check_project.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m unittest discover -s tests -p "test_*.py" -v
exit $LASTEXITCODE
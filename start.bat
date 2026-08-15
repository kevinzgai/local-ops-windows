@echo off
cd /d "%~dp0"

if /i "%~1"=="build" goto build
if /i "%~1"=="--build" goto build
if not "%~1"=="" goto run

:menu
echo ============================================
echo   总控台
echo   [1] 启动总控台（源码模式）
echo   [2] 打包 Windows 单文件 exe
echo   [0] 退出
echo ============================================
set /p choice=请选择 [1/2/0]：
if "%choice%"=="1" goto run
if "%choice%"=="2" goto build
exit /b 0

:run
python server.py %*
echo.
echo 总控台已停止。
pause
exit /b

:build
echo ============================================
echo   打包 Windows 单文件 exe
echo ============================================
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python。请先安装 Python 3.12 并勾选 "Add python.exe to PATH"。
    pause
    exit /b 1
)
echo [1/2] 检查构建依赖（pyinstaller / psutil）...
python -c "import PyInstaller, psutil" >nul 2>nul
if errorlevel 1 (
    echo 依赖缺失，正在安装 requirements-build.txt ...
    python -m pip install -r requirements-build.txt
    if errorlevel 1 (
        echo [错误] 构建依赖安装失败，请检查上方输出。
        pause
        exit /b 1
    )
)
echo.
echo [2/2] 打包单文件 windowed exe ...
python tools/build_exe.py
if errorlevel 1 (
    echo [错误] 打包失败，请检查上方输出。
    pause
    exit /b 1
)
echo.
echo 打包完成，产物在 dist 目录。
pause
exit /b 0

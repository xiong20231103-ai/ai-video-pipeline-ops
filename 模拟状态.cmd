@echo off
chcp 65001 >nul
set PYTHON=%LOCALAPPDATA%\TikHubOPS\venv\Scripts\python.exe
if not exist "%PYTHON%" (
  echo 请先运行“安装Dashboard.cmd”
  pause
  exit /b 1
)
echo.
echo 1. 正在识别字幕
echo 2. 正在2K导出
echo 3. 剪辑完成
echo 4. 剪辑失败
echo 5. 家庭电脑离线
echo 6. 清除模拟并恢复真实状态
echo.
set /p CHOICE=请选择：
if "%CHOICE%"=="1" "%PYTHON%" "%~dp0simulate.py" running
if "%CHOICE%"=="2" "%PYTHON%" "%~dp0simulate.py" exporting
if "%CHOICE%"=="3" "%PYTHON%" "%~dp0simulate.py" completed
if "%CHOICE%"=="4" "%PYTHON%" "%~dp0simulate.py" failed
if "%CHOICE%"=="5" "%PYTHON%" "%~dp0simulate.py" offline
if "%CHOICE%"=="6" "%PYTHON%" "%~dp0simulate.py" reset
echo.
pause

@echo off
chcp 65001 >nul
setlocal
set "DASHBOARD_VBS=%~dp0启动Dashboard_后台.vbs"
if not exist "%DASHBOARD_VBS%" (
  echo 找不到后台启动文件：%DASHBOARD_VBS%
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$target=$env:DASHBOARD_VBS; $startup=[Environment]::GetFolderPath('Startup'); $shell=New-Object -ComObject WScript.Shell; $shortcut=$shell.CreateShortcut((Join-Path $startup 'AI视频生产线Dashboard.lnk')); $shortcut.TargetPath=($env:WINDIR + '\System32\wscript.exe'); $shortcut.Arguments=('"' + $target + '"'); $shortcut.WorkingDirectory=(Split-Path -Parent $target); $shortcut.Description='AI视频生产线 OPS Dashboard（登录后后台启动）'; $shortcut.Save()"
if errorlevel 1 (
  echo 创建开机启动失败。
  pause
  exit /b 1
)
echo 已创建：登录 Windows 后后台启动“AI视频生产线Dashboard”。
pause

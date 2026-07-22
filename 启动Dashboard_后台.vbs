Option Explicit

'Starts the Dashboard watchdog without leaving a console window on the desktop.
Dim shell, fso, appDir, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
WScript.Sleep 8000
shell.CurrentDirectory = appDir
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & appDir & "\dashboard-watchdog.ps1"""
shell.Run command, 0, False

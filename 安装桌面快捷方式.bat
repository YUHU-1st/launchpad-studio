@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'Launchpad Studio MK2.lnk')); $s.TargetPath='%~dp0LaunchpadStudio.vbs'; $s.WorkingDirectory='%~dp0'; $s.Description='Launchpad Studio MK2 - tray service'; $s.Save()"
if errorlevel 1 (
  echo Failed to create desktop shortcut.
  pause
  exit /b 1
)
echo Desktop shortcut created.
pause

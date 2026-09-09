@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 exit /b 1
where uv >nul 2>nul
if not errorlevel 1 (
  uv pip install --python .venv\Scripts\python.exe pyinstaller
) else (
  .venv\Scripts\python.exe -m ensurepip --upgrade
  .venv\Scripts\python.exe -m pip install pyinstaller
)
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name "LaunchpadStudio" --collect-all pyaudiowpatch --hidden-import=pystray._win32 --add-data "tools\TemperatureHelper\publish;tools\TemperatureHelper\publish" --hidden-import=sounddevice --hidden-import=soundfile app.py
echo Build complete: dist\LaunchpadStudio\LaunchpadStudio.exe
pause

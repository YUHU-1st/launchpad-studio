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
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name "LaunchpadStudio" --specpath "build\spec" --collect-all pyaudiowpatch --collect-all winrt --collect-all pycaw --collect-all comtypes --collect-submodules aiohttp --hidden-import=pystray._win32 --add-data "%~dp0VERSION;." --add-data "%~dp0tools\TemperatureHelper\publish;tools\TemperatureHelper\publish" --add-data "%~dp0remote;remote" --add-data "%~dp0THIRD_PARTY_NOTICES.md;." --add-data "%~dp0licenses;licenses" --hidden-import=sounddevice --hidden-import=soundfile --hidden-import=glcontext.wgl app.py
powershell -NoProfile -Command "foreach ($name in @('icuuc.dll','icudt78.dll')) { $target=Join-Path (Get-Location) ('dist\LaunchpadStudio\_internal\'+$name); if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force } }"
echo Build complete: dist\LaunchpadStudio\LaunchpadStudio.exe
pause

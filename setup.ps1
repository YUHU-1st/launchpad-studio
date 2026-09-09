$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    if (-not (Test-Path .\.venv\Scripts\python.exe)) {
        & $uv.Source venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create Python environment." }
    }
    & $uv.Source pip install --link-mode copy --python .\.venv\Scripts\python.exe -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies." }
} else {
    $py = Get-Command python -ErrorAction Stop
    & $py.Source -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies." }
}
$helper = Join-Path $PSScriptRoot "tools\TemperatureHelper\publish\TemperatureHelper.exe"
if (-not (Test-Path $helper)) {
    $dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
    if ($dotnet) {
        & $dotnet.Source publish .\tools\TemperatureHelper\TemperatureHelper.csproj -c Release -r win-x64 --self-contained false -o .\tools\TemperatureHelper\publish
        if ($LASTEXITCODE -ne 0) { Write-Warning "Temperature helper could not be built; GPU temperature fallback remains available." }
    } else {
        Write-Warning ".NET SDK not found; GPU temperature fallback remains available."
    }
}
Write-Host "Setup complete. Double-click '启动 Launchpad Studio.vbs' to launch silently." -ForegroundColor Green

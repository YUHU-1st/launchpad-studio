param([switch]$SkipTests)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $repo "VERSION") -Raw).Trim()
$python = Join-Path $repo ".venv\Scripts\python.exe"
$pyinstaller = Join-Path $repo ".venv\Scripts\pyinstaller.exe"
$releaseDir = Join-Path $repo "release"
$releaseDist = Join-Path $repo "build\release-dist\$version"
$releaseWork = Join-Path $repo "build\release-work\$version"
$releaseSpec = Join-Path $repo "build\release-spec"

if (-not (Test-Path -LiteralPath $python)) { throw "Run setup.ps1 before building a release." }
if (-not (Test-Path -LiteralPath $pyinstaller)) { & $python -m pip install pyinstaller }

Push-Location $repo
try {
    if (-not $SkipTests) {
        & $python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }
        & $python app.py --self-test
        if ($LASTEXITCODE -ne 0) { throw "Desktop self-test failed." }
        node --check remote\app.js
        if ($LASTEXITCODE -ne 0) { throw "Remote JavaScript check failed." }
    }

    & $pyinstaller --noconfirm --clean --windowed --name LaunchpadStudio `
        --distpath $releaseDist --workpath $releaseWork --specpath $releaseSpec `
        --collect-all pyaudiowpatch --collect-all winrt --collect-all pycaw --collect-all comtypes `
        --collect-submodules aiohttp --hidden-import=pystray._win32 --hidden-import=sounddevice --hidden-import=soundfile `
        --add-data "$repo\VERSION;." --add-data "$repo\tools\TemperatureHelper\publish;tools\TemperatureHelper\publish" `
        --add-data "$repo\remote;remote" app.py
    if ($LASTEXITCODE -ne 0) { throw "Windows package build failed." }

    $desktopDir = Join-Path $releaseDist "LaunchpadStudio"
    $desktopExe = Join-Path $desktopDir "LaunchpadStudio.exe"
    $desktopTest = Start-Process -FilePath $desktopExe -ArgumentList "--self-test" -PassThru -Wait -WindowStyle Hidden
    if ($desktopTest.ExitCode -ne 0) { throw "Packaged desktop self-test failed." }

    $sdkCandidates = @($env:ANDROID_HOME, "D:\DevSpace\android-sdk", (Join-Path $env:LOCALAPPDATA "Android\Sdk")) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $sdk = $sdkCandidates | Select-Object -First 1
    if (-not $sdk) { throw "Android SDK was not found." }
    $env:ANDROID_HOME = $sdk
    $env:ANDROID_SDK_ROOT = $sdk
    gradle -p android clean assembleRelease lintRelease
    if ($LASTEXITCODE -ne 0) { throw "Android release build or lint failed." }

    $buildTools = Get-ChildItem -LiteralPath (Join-Path $sdk "build-tools") -Directory | Sort-Object Name -Descending | Select-Object -First 1
    $zipalign = Join-Path $buildTools.FullName "zipalign.exe"
    $apksigner = Join-Path $buildTools.FullName "apksigner.bat"
    $keystore = Join-Path $env:USERPROFILE ".android\debug.keystore"
    if (-not (Test-Path -LiteralPath $keystore)) { throw "The existing Android signing key was not found." }

    New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
    $windowsZip = Join-Path $releaseDir "LaunchpadStudio-$version-windows-x64.zip"
    $androidApk = Join-Path $releaseDir "LaunchpadStudioRemote-$version-android.apk"
    $alignedApk = Join-Path $releaseDir "LaunchpadStudioRemote-$version-android-aligned.apk"
    $unsignedApk = Join-Path $repo "android\app\build\outputs\apk\release\app-release-unsigned.apk"
    foreach ($target in @($windowsZip, $androidApk, $alignedApk)) {
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
    }

    Compress-Archive -Path (Join-Path $desktopDir "*") -DestinationPath $windowsZip -CompressionLevel Optimal
    & $zipalign -f -p 4 $unsignedApk $alignedApk
    if ($LASTEXITCODE -ne 0) { throw "Android zip alignment failed." }
    & $apksigner sign --ks $keystore --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out $androidApk $alignedApk
    if ($LASTEXITCODE -ne 0) { throw "Android signing failed." }
    & $apksigner verify --verbose --print-certs $androidApk
    if ($LASTEXITCODE -ne 0) { throw "Android signature verification failed." }
    Remove-Item -LiteralPath $alignedApk -Force

    $hashFile = Join-Path $releaseDir "SHA256SUMS.txt"
    $hashLines = foreach ($asset in @($windowsZip, $androidApk)) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $asset).Hash.ToLowerInvariant()
        "$hash  $([IO.Path]::GetFileName($asset))"
    }
    Set-Content -LiteralPath $hashFile -Value $hashLines -Encoding utf8
    Write-Host "Release $version is ready in $releaseDir" -ForegroundColor Green
}
finally {
    Pop-Location
}

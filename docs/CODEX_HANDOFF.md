# Launchpad Studio — Codex Development Handoff

Last updated: 2026-09-13

## 1. Objective

Extend the existing Windows Launchpad Studio desktop application with an Android client that can remotely control the PC over the same LAN. The Android client must control every desktop feature except game modes, and must also expose Windows system-media controls, Windows master volume, audio-output switching, media metadata, album art, synchronized lyrics, and playback progress/seek where the player supports it.

The implementation is already substantially underway in the user's Windows working tree:

`D:\DevSpace\launchpad-studio`

**Important:** that local working tree is newer than GitHub `main` and may contain uncommitted/untracked work. Treat the local tree as the source of truth until it has been inspected and reconciled. Do not reset/clean it.

## 2. Current architecture implemented locally

### Desktop LAN server

A new `core/remote.py` implements an `aiohttp` LAN server, normally on `0.0.0.0:8765`, protected by a six-digit PIN. It serves the mobile web UI and exposes HTTP/WebSocket endpoints. The WebSocket pushes a combined desktop/system-media state approximately every 250 ms and accepts remote commands.

Expected endpoints include:

- `/` mobile UI
- `/app.js`
- `/style.css`
- `/api/info`
- `/api/state`
- `/api/lyrics`
- `/api/cover/{cover_id}`
- `/ws`

The desktop app generates/stores a six-digit pairing PIN in local settings. Do not commit the user's PIN or `data/settings.json`.

### Windows media bridge

A new `core/windows_media.py` uses Windows Global System Media Transport Controls (GSMTC) plus `pycaw`.

Implemented locally:

- enumerate current Windows media session
- title / artist / album / subtitle
- playback state
- timeline position and duration when exposed by the player
- play / pause / toggle / stop / next / previous
- seek using GSMTC playback-position APIs
- repeat and shuffle where exposed
- Windows master volume and mute
- enumerate render endpoints
- switch default render endpoint for Console/Multimedia/Communications roles
- album-art extraction from WinRT thumbnail streams
- lyrics lookup through LRCLIB
- synchronized LRC parsing and current/next line calculation
- fallback media-key path through the existing macro/hotkey system

### Desktop application integration

`app.py` has local changes that:

- create/start/stop `SystemMediaBridge`
- create/start/stop `RemoteServer`
- expose a “手机遥控” dialog with address/PIN/status
- produce a JSON-serializable remote state snapshot
- enqueue remote commands back onto the Tk main thread
- route remote commands to existing video/music/live/performance/macro/device/preset/utility functions
- explicitly reject game control from mobile
- retain Session/game functionality on the desktop

The remote state includes Launchpad connection state, global lighting settings, performance data, macro-pad configuration, video/music/live state, permitted utilities, presets, and system media/audio state.

### Mobile web UI

A local `remote/` directory contains:

- `remote/index.html`
- `remote/style.css`
- `remote/app.js`

The UI currently has four main areas: Studio, Windows media, macros, and device settings. It is designed for touch and is loaded inside the Android WebView.

### Android wrapper app

A local `android/` Gradle project has been created. Package/application ID:

`io.github.yuhu.launchpadstudio.remote`

Known build configuration:

- compileSdk 35
- targetSdk 35
- minSdk 26
- current development version name: `1.1.0`
- portrait activity requested in manifest, although RC Plus can physically rotate and was observed in both orientations during automation
- INTERNET / ACCESS_NETWORK_STATE
- cleartext HTTP enabled because the PC LAN server is HTTP

The Android app is a small native connection shell plus WebView. It stores the PC address and pairing PIN in app-private SharedPreferences and loads the desktop-hosted mobile UI.

During RC Plus testing, a debug/automation path was also added so ADB can launch the activity with connection parameters and avoid DJI/Gboard punctuation conversion during automated input. Inspect current local `MainActivity.java` for the exact Intent extra names before using this path.

For debug builds, WebView debugging was enabled so Chrome DevTools Protocol can inspect and drive the real page running inside RC Plus.

## 3. Dependencies added locally

`requirements.txt` was extended with packages approximately equivalent to:

```text
aiohttp>=3.10
pycaw>=20240210
comtypes>=1.4
winrt-runtime>=3.1
winrt-Windows.Foundation>=3.1
winrt-Windows.Foundation.Collections>=3.1
winrt-Windows.Media>=3.1
winrt-Windows.Media.Control>=3.1
winrt-Windows.Storage.Streams>=3.1
```

`build_exe.bat` was also extended to collect WinRT, pycaw, comtypes, aiohttp, pyaudiowpatch, the remote web assets, and the existing temperature helper.

`.gitignore` has local additions for Android build output and local Android settings.

## 4. Automated tests already completed before RC Plus testing

Before the latest device fixes, the following passed locally:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result at that stage: 11/11 tests passed.

```powershell
.venv\Scripts\python.exe app.py --self-test
```

Passed.

```powershell
node --check remote\app.js
```

Passed.

A desktop smoke test also successfully created the Tk app, started the remote server, generated remote state, and shut down cleanly.

The Android debug APK was successfully built and verified with APK Signature Scheme v2. The APK path in the current local tree is normally:

`android\app\build\outputs\apk\debug\app-debug.apk`

Re-run all tests after reconciling the latest Android fixes.

## 5. Real DJI RC Plus test results

Device successfully detected through ADB:

```text
serial: 4LFCK4D0024PX4
product: rm700
model: DJI_RC_Plus
device: rm700
Android: 10
API level: 29
ABI: arm64-v8a
```

Windows already had a working Microsoft WinUSB ADB driver for the device (`winusb.inf`).

The APK installed successfully with `adb install -r` and launched successfully.

Observed RC Plus display/UI characteristics during testing:

- approximately 1200 × 1880 in portrait UI dump
- approximately 1920 × 1160 in landscape contexts
- bundled/system WebView reported Chromium 95.0.4638.50

### Android 10 crash found and fixed

A real compatibility defect was discovered:

```text
java.lang.NoSuchMethodError:
No static method encode(String, java.nio.charset.Charset)
in java.net.URLEncoder
```

The app used `URLEncoder.encode(String, Charset)`, which is not available on this Android 10 runtime. Because the pairing token is always a six-digit numeric PIN, the implementation was changed to use the PIN directly rather than this unavailable overload.

After rebuilding/reinstalling, the activity remained stable in the foreground and loaded the remote WebView successfully.

### LAN connection verified on real hardware

At the time of the successful test, PC and RC Plus were on the same `192.168.10.x` LAN. TCP connections from the RC Plus to PC port `8765` were observed as `Established`, and the WebSocket inside the real RC Plus WebView reported OPEN.

Do not hard-code the test IPs; resolve/display the current LAN address dynamically.

### WebView DevTools verified

ADB port-forwarding to the WebView DevTools socket worked. `/json` returned the real page:

`Launchpad Studio Remote`

with the LAN URL and token query parameter. A small local Node helper (`tools/rcplus_cdp_eval.mjs` at the time of testing) was created to execute JavaScript through Chrome DevTools Protocol. Decide whether to keep it as a documented debug tool (prefer moving under `tools/debug/`) or remove it before release.

### Real system-media state reached the RC Plus

The RC Plus WebView received a real Windows media session from NetEase Cloud Music:

```text
app: cloudmusic.exe
title: IF YOU
artist: BIGBANG
status: paused
```

The phone also received:

- album-art `cover_id`
- a lyrics key
- synchronized lyrics from LRCLIB
- current/next lyric state
- Windows master volume
- current default audio output
- full list of active render endpoints

The output list during this test included AG06/AG03, Realtek Audio, NoMachine audio, and a NetEase virtual audio endpoint. This confirms that media/audio data streaming and device enumeration are working end-to-end on the real RC Plus.

## 6. Highest-priority unresolved defects

### A. NetEase play/pause compatibility

From the real RC Plus page, pressing the system-media play button sent the WebSocket command, but NetEase remained paused in the observed test.

Investigate both paths:

1. `session.try_toggle_play_pause_async()` return/result and timing.
2. media-key fallback behavior in `core/windows_media.py` / `core.macros`.

Current fallback mapping treats `play` and `pause` as the same `PLAY` media key, which can be semantically wrong if a player reports stale state. Consider using distinct virtual media keys only where Windows exposes them, or carefully choose toggle behavior based on capability/state.

Test against at least NetEase Cloud Music, PotPlayer, and AIMP if available.

### B. NetEase timeline/seek unavailable in the tested session

NetEase reported:

```text
duration = 0
position = 0
can_seek = false
controls.seek = false
```

Therefore the RC Plus could not yet validate system-media progress seeking for that session. This may be a player limitation/state issue rather than a server bug.

Required follow-up:

- test while actively playing
- test another player that exposes GSMTC timeline/seek (e.g. PotPlayer/AIMP depending configuration)
- keep seek disabled or visually unavailable when `can_seek == false`
- do not invent duration/position values
- if NetEase requires a separate compatibility adapter, implement it cleanly rather than breaking the GSMTC generic path

### C. Mobile video/music play button logic

Inspect `remote/app.js`. At one point the buttons were statically wired to:

```js
command("video.pause")
command("music.pause")
```

while the button label can show “播放” when idle. Ensure the click handler sends `video.play` / `music.play` when not running and pause/resume appropriately when already running.

### D. Full non-game regression still incomplete

The RC Plus has not yet completed real-device coverage for every remote command. Finish real touch/WebView tests for performance mode, macros, video, music visualization, live audio, clock/calendar/weather/focus timer, presets, MIDI/Launchpad reconnect/test, global brightness/palette/custom color, blackout, and stop-all.

Games must remain excluded from the mobile command surface.

### E. Desktop packaged build still needs final validation

The updated PyInstaller build should be executed after the media/Android fixes. Verify that the frozen build includes all `winrt-*`, aiohttp, pycaw/comtypes, pyaudiowpatch, remote web assets, and existing helper binaries. Then test the remote server and GSMTC functionality from the packaged executable, not only from `.venv` Python.

## 7. Recommended next execution order

1. Inspect the local dirty working tree before doing anything else.
2. Preserve and review the current Android 10 fixes in `MainActivity.java`.
3. Fix `remote/app.js` video/music idle play logic if still present.
4. Add detailed logging around GSMTC command return values and fallback execution.
5. Re-test NetEase play/pause from the RC Plus through WebView/CDP.
6. Test timeline/seek using a player that exposes duration and position.
7. Test master volume/mute and switch AG06/AG03 ↔ Realtek from RC Plus, then restore the user's original output/volume.
8. Complete all non-game remote feature tests.
9. Run Python unit tests, app self-test, JS syntax check, Android build/install, and `adb logcat` crash scan.
10. Build and smoke-test the Windows packaged application.
11. Review `git diff --check`, remove or organize temporary debugging files, commit/push source, then produce a release APK (and preferably a Windows package) only after the above passes.

## 8. Environment notes from the development machine

Repository:

`D:\DevSpace\launchpad-studio`

Android SDK used during development:

`D:\DevSpace\android-sdk`

Working Java 17 installation detected:

`C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot`

Gradle available globally during the session: 9.3.1.

The Android project uses Android Gradle Plugin 8.7.3. A Gradle wrapper had not yet been successfully added because downloading the wrapper distribution failed during the earlier session. Building with the installed Gradle command succeeded.

Typical debug build command:

```cmd
set "ANDROID_HOME=D:\DevSpace\android-sdk"
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot"
gradle -p android assembleDebug
```

ADB was available at:

`D:\platform-tools\adb.exe`

## 9. Git/release state at handoff

The large LAN/Android implementation described above was developed in the local Windows working tree and was **not yet confirmed pushed to GitHub main** when this handoff was created. GitHub `main` should therefore not be assumed to contain the implementation just because these documentation files exist.

Before any pull/reset/rebase:

```cmd
cd /d D:\DevSpace\launchpad-studio
git status --short
git diff --stat
git diff --check
git ls-files --others --exclude-standard
```

Inspect the output and preserve all relevant changes.

No final public release should be considered complete yet. The last APK was a debug-signed sideload build used for RC Plus testing.

## 10. Definition of “done”

The task is complete only when a normal user can install/start the Windows app, install the Android APK, pair on the same LAN, remotely control every required non-game feature, control compatible Windows media players, see streaming media metadata/cover/lyrics/progress, seek where the player exposes seek support, adjust system volume/mute, switch audio outputs, reconnect cleanly after interruption, and do so without crashes on the tested RC Plus Android 10 device.

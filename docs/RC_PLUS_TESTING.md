# DJI RC Plus Real-Device Test Guide

Last updated: 2026-09-13

This document records the working real-device test setup used for the Android LAN remote.

## Device baseline

Tested hardware:

```text
DJI RC Plus
product/device: rm700
serial: 4LFCK4D0024PX4
Android: 10
API: 29
ABI: arm64-v8a
```

ADB on the Windows machine was available at:

`D:\platform-tools\adb.exe`

A successful detection looks like:

```text
4LFCK4D0024PX4  device  product:rm700 model:DJI_RC_Plus device:rm700
```

If the device is absent, unlock the RC Plus, set USB use to file transfer/MTP, confirm USB debugging authorization, restart the ADB daemon, and replug the cable if necessary. Windows previously used Microsoft `winusb.inf` successfully for the ADB interface.

## Basic device verification

```cmd
D:\platform-tools\adb.exe devices -l
D:\platform-tools\adb.exe shell getprop ro.product.model
D:\platform-tools\adb.exe shell getprop ro.product.device
D:\platform-tools\adb.exe shell getprop ro.build.version.release
D:\platform-tools\adb.exe shell getprop ro.build.version.sdk
D:\platform-tools\adb.exe shell getprop ro.product.cpu.abi
```

## Build Android debug APK

From `D:\DevSpace\launchpad-studio`:

```cmd
set "ANDROID_HOME=D:\DevSpace\android-sdk"
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot"
gradle -p android assembleDebug
```

Expected APK:

`android\app\build\outputs\apk\debug\app-debug.apk`

## Install/update APK

```cmd
D:\platform-tools\adb.exe install -r android\app\build\outputs\apk\debug\app-debug.apk
```

Confirm package:

```cmd
D:\platform-tools\adb.exe shell pm path io.github.yuhu.launchpadstudio.remote
```

## Launch and foreground verification

Normal launch:

```cmd
D:\platform-tools\adb.exe shell monkey -p io.github.yuhu.launchpadstudio.remote -c android.intent.category.LAUNCHER 1
```

The latest local debug build also contains an ADB/automation launch path that can inject the PC address and PIN via Intent extras. Inspect `MainActivity.java` for the exact extra names before use; do not guess them.

Foreground checks:

```cmd
D:\platform-tools\adb.exe shell dumpsys window windows | findstr /i "launchpadstudio MainActivity"
D:\platform-tools\adb.exe shell pidof io.github.yuhu.launchpadstudio.remote
```

## UI hierarchy

```cmd
D:\platform-tools\adb.exe shell uiautomator dump /sdcard/launchpad_ui.xml
D:\platform-tools\adb.exe shell cat /sdcard/launchpad_ui.xml
```

This was useful for confirming the native shell and connection overlay. Once the WebView is connected, Android's UI hierarchy does not expose the internal HTML controls in detail; use WebView DevTools for those.

## Important RC Plus automation quirk

During ADB text injection, the RC Plus Gboard converted URL punctuation to full-width Chinese punctuation, producing strings similar to:

```text
HTTP：／／192.168...
```

This breaks URL parsing. Do not rely on `adb shell input text` for the connection URL on this device. Use the debug Intent-extra path, app-private test setup, or another deterministic method.

## Android 10 compatibility regression that was found

The original Android wrapper used:

```java
URLEncoder.encode(pin, StandardCharsets.UTF_8)
```

On this Android 10 runtime it produced:

```text
java.lang.NoSuchMethodError:
No static method encode(Ljava/lang/String;Ljava/nio/charset/Charset;)Ljava/lang/String;
```

Because the token is a six-digit numeric PIN, the local implementation was changed to use the validated PIN directly. Do not reintroduce an API-level-incompatible overload.

## Logcat crash check

Clear before a focused test:

```cmd
D:\platform-tools\adb.exe logcat -c
```

After the test:

```cmd
D:\platform-tools\adb.exe logcat -d -b crash
D:\platform-tools\adb.exe logcat -d | findstr /i "launchpadstudio AndroidRuntime chromium WebView"
```

The DJI firmware emits many unrelated DUSS/link/USB errors. Filter primarily by the app package/PID and AndroidRuntime before treating logs as application failures.

## Desktop server verification

The desktop remote service currently uses port 8765 by default.

On Windows:

```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
```

The API health endpoint should return JSON from:

```text
/api/info?token=<PIN>
```

Do not place the real PIN in committed scripts or documentation.

During the successful test, established TCP connections from RC Plus to the Windows host confirmed real LAN communication.

## WebView DevTools / CDP workflow

The local debug build was modified to enable WebView debugging only when the Android application itself is debuggable.

After launching the debug APK, find the socket:

```cmd
D:\platform-tools\adb.exe shell cat /proc/net/unix | findstr webview_devtools_remote
```

A socket similar to this was observed:

```text
@webview_devtools_remote_<pid>
```

Forward it to the PC (replace socket suffix as needed):

```cmd
D:\platform-tools\adb.exe forward tcp:9222 localabstract:webview_devtools_remote_<pid>
```

Then inspect:

```text
http://127.0.0.1:9222/json
```

The successful RC Plus test returned a page titled `Launchpad Studio Remote`, with a `webSocketDebuggerUrl`. Chrome DevTools Protocol can then evaluate JavaScript directly inside the real RC Plus WebView.

A temporary Node helper was created locally as `tools/rcplus_cdp_eval.mjs`. Before release, either:

- move it to `tools/debug/` and document it as a developer-only utility, or
- remove it if it is no longer needed.

Do not ship debug WebView tooling in a release build.

## Suggested CDP assertions

Useful values to query inside the RC Plus page:

```js
document.title
connection?.textContent
ws?.readyState
state?.launchpad
state?.system_media
state?.video
state?.music
state?.live
state?.utilities
```

For actual interaction, invoke the same DOM click/change events a user would trigger rather than only calling desktop APIs from the PC. This verifies the full path:

RC Plus WebView → JavaScript → WebSocket → aiohttp server → Tk command queue / SystemMediaBridge → Windows/Launchpad → state pushed back to RC Plus.

## Real media test already observed

The RC Plus received the following real GSMTC session from NetEase Cloud Music:

```text
source app: cloudmusic.exe
title: IF YOU
artist: BIGBANG
status: paused
```

The RC Plus also received cover data, synchronized lyrics, Windows master volume, active/default audio output, and a list of render endpoints.

However, pressing play from the RC Plus did not make NetEase leave the paused state during that test. Treat play/pause compatibility as unresolved until retested after changes.

NetEase also reported no usable timeline in that specific session:

```text
duration: 0
position: 0
can_seek: false
```

Seek must therefore be tested with an active player/session that exposes a valid timeline. Do not mark seek complete based only on frontend slider behavior.

## Audio-output test safety

When testing output switching:

1. Record the original active output and master volume.
2. Change to a second real output from the RC Plus.
3. Confirm Windows default output actually changed.
4. Change back to the original output.
5. Restore the original volume/mute state.

This avoids leaving the user's machine unexpectedly routed to the wrong device.

## Final RC Plus regression checklist

Before release, exercise the real RC Plus through the Android UI for:

- reconnect/pairing
- Launchpad device refresh/connect/test
- palette/brightness/custom color/blackout
- performance monitor
- macros
- video playback/control/settings/presets
- music visualization/control/settings/presets
- live input visualization
- clock/calendar/weather/focus timer
- stop-all
- Windows media controls
- cover/lyrics/progress updates
- volume/mute
- output switching and restoration

Do not add or test mobile game controls; those are intentionally out of scope.

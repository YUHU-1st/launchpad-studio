# Android LAN Remote — Requirements and Acceptance Criteria

Last updated: 2026-09-13

## Product goal

Add an Android remote-control client for Launchpad Studio. The Android device and Windows PC are on the same local network. The mobile client must remotely control the desktop application's non-game functions and provide a Windows system-media remote experience.

## Functional requirements

### 1. Pairing and LAN connectivity

- Desktop exposes a LAN service on a configurable port (currently 8765 by default).
- Desktop shows reachable LAN address(es) and a six-digit pairing PIN.
- Android can save the PC address and PIN locally and reconnect automatically.
- PIN-protected requests must reject unauthenticated clients.
- Client must recover from temporary Wi-Fi loss, desktop restart, or WebSocket disconnect without requiring app reinstall.
- No cloud account is required for LAN control.

### 2. Desktop feature coverage from Android

Android must control all existing non-game functions, including:

- Launchpad/MIDI device model selection and connection
- device refresh and lighting test
- global palette/theme selection
- brightness
- custom color
- blackout
- global stop
- macro-control toggle
- performance-monitor mode
- macro-pad display, trigger, edit, save, test, and clear
- video pixel player: playlist selection, play/pause/resume, previous/next, seek, speed, loop, effects, detailed parameters, presets
- music visualization/player: playlist selection, play/pause/resume, previous/next, seek, speed, loop, playback volume, visualization style, detailed parameters, presets
- live audio visualization: input device, start/stop behavior, style, detailed parameters, presets
- desktop utilities: digital clock, calendar, weather, focus timer and their relevant settings

### 3. Explicitly excluded from Android

Game modes must not be remotely controllable from Android. This includes existing game-oriented utilities/modes such as snake, whack-a-mole, rhythm games, waterfall/maimai-style games, or other game functions added later.

The desktop may continue to provide these modes locally.

### 4. Windows system-media control

The Android client must provide controls for compatible Windows media applications such as NetEase Cloud Music, PotPlayer, and AIMP where Windows/player APIs permit it.

Required controls:

- play / pause / toggle
- previous track
- next track
- stop where supported
- seek/progress control where the active player exposes a valid timeline
- repeat mode where supported
- shuffle where supported

The implementation should use Windows GSMTC as the generic path and may use safe media-key fallbacks when an application does not honor a GSMTC command.

Do not falsely report seek support. If a player reports no duration/timeline/seek capability, the mobile UI must make that limitation clear or disable seeking for that session.

### 5. Media information streamed to Android

The mobile client should receive and render in near real time:

- source application
- title
- artist
- album/subtitle when available
- play/pause state
- current position
- total duration when available
- album artwork
- current synchronized lyric line
- next lyric line
- full lyrics view
- repeat/shuffle state

Lyrics may be resolved through LRCLIB when the player does not provide lyrics directly. Failure to fetch lyrics must not break media controls.

### 6. Windows audio control

Android must support:

- master output volume
- mute/unmute
- display active Windows render endpoint
- enumerate active render endpoints
- switch the default render endpoint

The intended use case includes switching between devices such as onboard Realtek audio and a USB audio interface (for example Yamaha AG06/AG03).

When switching the default output, update Console, Multimedia, and Communications roles together unless a future UI deliberately exposes separate roles.

### 7. Android compatibility

Known required real device:

- DJI RC Plus
- model/device: `rm700`
- Android 10
- API 29
- arm64-v8a
- Chromium/WebView 95 observed during testing

Do not depend on Java/Android APIs that are unavailable on API 29 merely because the project compiles against API 35.

The app should also remain usable on ordinary Android phones/tablets meeting `minSdk`.

## Non-functional requirements

### Security and scope

- LAN-oriented design; do not expose a public Internet control service by default.
- Require pairing PIN for state/control endpoints.
- Never expose game controls through the mobile API/UI.
- Do not add arbitrary unauthenticated command execution.
- Existing macro/command features should only be reachable through the authenticated remote surface and should preserve current desktop behavior.

### Responsiveness

- WebSocket state updates should feel live; approximately 4 Hz is currently acceptable for general state.
- Progress/lyrics should update smoothly enough to be usable.
- Seek/volume sliders should throttle network commands to avoid flooding the desktop.

### Reliability

- Desktop UI operations must remain on the Tk main thread.
- Background media/network threads must shut down cleanly when the desktop app closes.
- A mobile disconnect must not crash or freeze the desktop app.
- Unsupported player capabilities must degrade gracefully.

### Packaging

Windows package must include all Python/WinRT/audio/web dependencies and `remote/` assets.

Android deliverable must be an installable APK. Debug-signed builds are acceptable for development/RC Plus testing; a final release should use a stable signing strategy before distribution as a normal release build.

## Acceptance test matrix

### Connectivity

Pass when:

- APK installs on DJI RC Plus.
- Android pairs with desktop on the same LAN.
- Authenticated HTTP state works.
- WebSocket connects and receives live state.
- Wrong PIN is rejected.
- Disconnect/reconnect works after Wi-Fi or desktop restart.

### Launchpad and studio control

Pass when the RC Plus can trigger and observe state changes for every required non-game function listed above, and the corresponding Launchpad/desktop behavior occurs.

### System media

Pass when real RC Plus controls are tested against at least one Windows media player end-to-end for play/pause/previous/next. Seek must additionally be verified against a player/session that reports a valid GSMTC timeline.

For NetEase Cloud Music specifically, metadata/cover/lyrics are already known to stream successfully; playback command compatibility still needs completion.

### Audio outputs

Pass when RC Plus can display the current output list, change volume/mute, switch between at least two real output endpoints, observe the default change, and restore the user's original output afterward.

### Stability

Pass when repeated navigation/control does not produce Android crashes, Python exceptions, stuck WebSockets, or desktop UI thread errors, and `adb logcat` shows no app FATAL EXCEPTION during the final test run.

## Out of scope unless separately requested

- controlling game modes from Android
- public Internet relay/cloud remote access
- DRM/media extraction
- bypassing player security restrictions
- streaming Windows audio itself to the Android device
- replacing the user's media player UI completely

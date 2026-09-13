# Codex Instructions

This repository is actively being extended with a LAN Android remote-control client. Before making changes, read:

- `docs/CODEX_HANDOFF.md`
- `docs/REMOTE_ANDROID_REQUIREMENTS.md`
- `docs/RC_PLUS_TESTING.md`

## Critical workflow rules

1. The user's Windows working tree at `D:\DevSpace\launchpad-studio` may contain substantial **uncommitted** Android/LAN-remote work that is newer than `main`. Inspect `git status`, `git diff`, untracked files, and the current running app before pulling, resetting, rebasing, cleaning, or switching branches.
2. Do **not** run `git reset --hard`, `git clean -fd`, overwrite the working tree from GitHub, or discard local changes unless the user explicitly asks.
3. Preserve all existing desktop features. Mobile remote control must cover all non-game features; game modes must remain unavailable from mobile.
4. Prefer complete, testable fixes over partial patches. After each meaningful change, run the relevant unit/self-tests and, when the DJI RC Plus is connected, perform real ADB/WebView tests on that device.
5. The Android target includes DJI RC Plus (`rm700`, Android 10 / API 29, arm64-v8a). Avoid APIs unavailable on API 29 even if `compileSdk` is newer.
6. Do not commit generated Android build directories, `.venv`, local SDKs, local settings/PINs, screenshots, logcat dumps, or temporary test artifacts.
7. Keep the LAN remote server private-network oriented: PIN authentication, no game control, and no destructive PC actions beyond the existing explicitly exposed remote commands.
8. Before declaring completion, verify Windows desktop packaging, Android APK build/install, LAN pairing/reconnect, media control, seek where supported, audio output switching, lyrics/cover/progress streaming, and all non-game desktop modes.

## Current priority

The highest-priority unresolved area is Windows system-media compatibility, especially NetEase Cloud Music: metadata/cover/lyrics stream successfully, but play/pause and timeline/seek behavior still need compatibility work and real-device verification. Continue from the handoff document rather than reimplementing the architecture from scratch.

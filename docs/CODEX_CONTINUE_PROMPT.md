# Ready-to-use Codex continuation prompt

Copy the following into Codex when resuming work from the Windows development machine.

---

Continue development of `D:\DevSpace\launchpad-studio` from the current local working tree.

First read `AGENTS.md`, `docs/CODEX_HANDOFF.md`, `docs/REMOTE_ANDROID_REQUIREMENTS.md`, and `docs/RC_PLUS_TESTING.md`.

The local working tree contains newer, potentially uncommitted Android/LAN-remote work that may not yet exist on GitHub `main`. Before changing anything, run and inspect:

```cmd
cd /d D:\DevSpace\launchpad-studio
git status --short
git diff --stat
git diff --check
git ls-files --others --exclude-standard
```

Do not run `git reset --hard`, `git clean -fd`, overwrite the tree from remote, or discard any existing local work. Reconcile the current code as the source of truth first.

Goal: finish the same-LAN Android remote for Launchpad Studio. The Android client must control every non-game desktop feature, must not expose game modes, and must provide Windows media remote control, master volume/mute, audio-output switching, metadata, cover, lyrics, and progress/seek when the player exposes a usable timeline.

A DJI RC Plus is the primary real test device:

```text
model: DJI RC Plus / rm700
Android 10 / API 29
arm64-v8a
ADB serial: 4LFCK4D0024PX4
```

The latest real-device work already found and fixed an Android 10 crash caused by `URLEncoder.encode(String, Charset)`. Preserve that fix. Debug WebView/CDP testing was also added locally; keep it developer-only and do not expose it in a release build.

Highest priority unresolved issue: NetEase Cloud Music metadata/cover/lyrics/audio-device state reaches the real RC Plus successfully, but pressing system-media play from the RC Plus did not change NetEase from paused during the last test. NetEase also reported `duration=0`, `position=0`, `can_seek=false` in that session. Investigate GSMTC command return values and media-key fallback; test seek with a player/session that exposes a valid timeline. Do not fake timeline support.

Also inspect `remote/app.js`: ensure video/music buttons send play when idle rather than always sending pause. Complete real RC Plus regression for all non-game modes.

Use the existing architecture (`core/remote.py`, `core/windows_media.py`, `remote/`, Android wrapper) rather than rewriting it unnecessarily.

After each fix, perform actual tests instead of only describing what would be done. Run at minimum:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe app.py --self-test
node --check remote\app.js
```

Build/install the Android debug APK and test through ADB/WebView on RC Plus. Check `adb logcat -b crash`. For media/output testing, restore the user's original audio output and volume after the test.

After the Android/media path is stable, build and smoke-test the Windows PyInstaller package, inspect `git diff --check`, organize/remove temporary debug artifacts, commit the implementation, push it to the GitHub repository, and only then create the final installable APK/release artifacts.

Do not stop at a planning message unless there is a genuine blocker. Continue until the current round produces actual code changes and verifiable test results, then report exactly what changed, what passed, and what remains.

---

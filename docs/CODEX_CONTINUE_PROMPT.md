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

Completion update (2026-09-14): explicit NetEase play and pause now work from the RC Plus after correcting GSMTC results, state-aware media-key fallback, and COM MTA initialization. Video/music idle play and pause/resume logic is fixed, all non-game remote modes passed RC Plus regression, and the packaged Windows server passed an authenticated API smoke test. NetEase still reports `duration=0`, `position=0`, `can_seek=false`; the remote correctly disables seek for that session rather than inventing a timeline.

Use the existing architecture (`core/remote.py`, `core/windows_media.py`, `remote/`, Android wrapper) rather than rewriting it unnecessarily.

After each fix, perform actual tests instead of only describing what would be done. Run at minimum:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe app.py --self-test
node --check remote\app.js
```

Build/install the Android debug APK and test through ADB/WebView on RC Plus. Check `adb logcat -b crash`. For media/output testing, restore the user's original audio output and volume after the test.

For future changes, repeat the Python, JavaScript, Android, packaged-Windows, and RC Plus regression checks before publishing replacement release artifacts.

Do not stop at a planning message unless there is a genuine blocker. Continue until the current round produces actual code changes and verifiable test results, then report exactly what changed, what passed, and what remains.

---

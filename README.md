# Launchpad Studio

A Windows desktop controller for the Novation Launchpad family. It combines a model-aware LED canvas, live PC telemetry, programmable macro pads, pixel video playback, analysed music shows, low-latency audio-reactive lighting, desktop utilities and small games.

**Windows users:** download the ready-to-run package from [Latest Release](https://github.com/YUHU-1st/launchpad-studio/releases/latest), extract it, and run `LaunchpadStudio.exe`. No Python installation is required.

## Start

1. Connect the Launchpad and close Ableton/other programs that may own its MIDI port.
2. Double-click `LaunchpadStudio.vbs` (or `start.bat`). It starts silently with no terminal window. The first run prepares the local environment in the background; later runs open immediately.
3. Choose automatic model detection (recommended) and the Launchpad MIDI input/output, then click **Connect**. If a Windows MIDI driver exposes a generic name, select the exact model manually.

Run `安装桌面快捷方式.bat` once if you want a desktop shortcut. The shortcut uses the silent VBS launcher.

Closing the visual window keeps Launchpad Studio running in the notification area. MIDI input, macros, monitoring and active light shows continue. Right-click the tray icon to reopen the visual interface or completely exit. Launching the app again activates the existing instance instead of creating a duplicate service.

Opening another mode page only changes the visible controls: the current light show continues uninterrupted. A new mode takes over the Launchpad only after you press its Start/Play/Enable button. The Macro page has an explicit **Enable Macro Pad Lighting** button for the same reason.

The on-screen device changes to the detected hardware layout. Standard models show the 8×8 grid plus top/right controls; Pro models also expose their left and bottom rows.

## Notes

- Video playback requires OpenCV (installed automatically).
- Music files supported by the local audio backend usually include WAV, MP3, OGG and FLAC.
- Audio and video pages include persistent playlists, draggable seek bars, previous/next, play/pause, 0.5×–3× speed and off/single/list loop modes. Audio also has output volume.
- Audio-reactive modes provide 10 effects (spectrum, mirrored spectrum, waveform, pulse, ripple, nebula, rain, flame, tunnel and checkerboard) with frequency band, dB range, sensitivity, noise gate, animation speed and spread controls.
- Video supports original color, heatmap, edge, monochrome glow, kaleidoscope and glitch filters with saturation, contrast, gamma and edge threshold controls.
- Every detail parameter is saved automatically and restored on the next launch. Each effect page can reset defaults, save/load named presets, pick recently used presets, and copy/paste matching parameters between music, live-input and video modes.
- **Tools & Games** includes a scrolling digital clock, calendar, current weather, focus timer, Snake and Whack-a-Mole. Both games have Easy/Normal/Hard difficulty, automatic levels, live scoreboards, persistent high scores and a short edge-wave celebration on every point. Snake wraps across every edge and uses the Launchpad's physical top-row `↑ ↓ ← →` controls; Whack-a-Mole grants a fresh reaction window after every hit and is played by pressing the lit physical pad.
- Weather uses the Open-Meteo geocoding and forecast APIs, requires no API key, caches results for ten minutes, and fails safely when offline.
- “System audio” capture uses Windows WASAPI loopback when the audio backend exposes a loopback device; otherwise select a microphone.
- Performance mode reads CPU, GPU, motherboard and storage temperatures through the bundled LibreHardwareMonitor helper. Some laptop CPU and motherboard sensors require **Run with administrator privileges**; use the button in Performance mode when a value says permission is required.
- Macro profiles, last-used parameters and named presets are saved to `data/settings.json`.
- Python and native crash diagnostics are written to `data/crash.log` and `data/native_crash.log`.
- `build_exe.bat` creates a distributable Windows build.

Supported model profiles: Launchpad MK1, Launchpad S, Launchpad Mini MK1/MK2/MK3, Launchpad MK2, Launchpad X, Launchpad Pro and Launchpad Pro MK3. RGB-capable devices receive full RGB output; legacy red/green models receive an automatic closest-color conversion that respects their physical LED limitations.

## Development

Run the core regression suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The application is Windows-only because its MIDI backend uses WinMM. Weather data is provided by [Open-Meteo](https://open-meteo.com/). Launchpad is a trademark of Focusrite Audio Engineering Ltd.; this independent project is not affiliated with or endorsed by Novation.

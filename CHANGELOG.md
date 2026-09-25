# Changelog

## 2.1.1 - 2026-09-25

- Made desktop utilities, Snake, Whack-a-Mole, Waterfall Rhythm and radial rhythm render natively across the complete multi-Launchpad canvas instead of stretching an 8×8 image.
- Mapped presses from every tile to its real composite-canvas coordinate so food, targets and rhythm notes remain playable on every connected Launchpad.
- Fixed Launchpad X macro presses by storing macros by physical pad position, reading older model-specific profiles, and allowing configured pads to trigger directly from the Macro Pads page.

## 2.1.0 - 2026-09-25 — Live Matrix

- Added an always-on, proportionally scaled live composite preview of every connected Launchpad to every desktop and Android/LAN mode.
- Added direct drag-to-move and drag-to-swap layout editing from the live desktop and mobile canvases.
- Replaced manual MIDI-port setup with one-tap Launchpad discovery and connection.
- Promoted Layout Settings to a top-level desktop/mobile page with graphical Extended, Mirror, and Independent routing choices.
- Removed per-device mode assignment from Extended and Mirror routing; it now appears only when Independent mode is selected.
- Streamed the actual LED state of every connected device to the mobile preview and corrected dark-theme select/dropdown contrast.

## 2.0.0 - 2026-09-23 — Matrix

- Added multi-Launchpad layouts with persistent device numbers, MIDI ports, models and X/Y tile positions.
- Added extended-canvas, mirrored-output and independent-mode routing across multiple Launchpads.
- Added native wide video pixels, performance bars and audio-spectrum rendering for extended layouts.
- Added on-device numeric identification and per-device input routing so games and macros do not interfere with other assigned modes.
- Added the complete Matrix device editor to the Android/LAN remote, including canvas preview, device add/remove, numbering, positioning, per-device modes, model and MIDI-port assignment, LED identification and connection.
- Added abbreviated Windows MIDI-name detection for Launchpad X, Launchpad Mini MK3 and Launchpad Pro MK3.
- Named the major release **Launchpad Studio 2 · Matrix** and centralized the desktop and Android version at `2.0.0`.

## 1.4.0 - 2026-09-13

- Added a PIN-protected same-LAN Android remote for every non-game desktop mode, Launchpad device setup, global lighting controls, macros and presets.
- Added Windows system-media metadata, album art, synchronized lyrics, play/pause/previous/next, capability-aware seeking, master volume, mute and default-output switching.
- Fixed NetEase Cloud Music play/pause by sending explicit commands and using state-aware media-key fallback when GSMTC rejects a request.
- Fixed Windows audio commands from the media worker by initializing COM in multithreaded mode.
- Added Android 10 compatibility for DJI RC Plus and kept WebView debugging disabled in release builds.
- Fixed idle video/music remote buttons and disabled unavailable media controls instead of presenting a fake timeline.

## 1.3.0 - 2026-09-10

- Added independent clearing of a selected macro pad and expanded macro actions with PowerShell, mouse, system, volume and multi-step workflows.
- Added persistent parallel macro control to every non-game mode without changing the active lighting frame.
- Added auto-chart Waterfall and radial arcade-style rhythm games with beat/transient/frequency analysis, three difficulties, 1–5 note speed, 4–8 lanes, pause, timing grades, combo, accuracy and high scores.
- Added a global Stop All and Black Out action in the application header.
- Fixed the right-side inspector width at the default window size.
- Replaced the README with complete Chinese and English documentation, screenshots for every mode and game, a full overview video and ten individual feature videos.

## 1.2.0 - 2026-09-10

- Added a non-blocking, palette-aware score celebration effect to both games.
- Separated the visible configuration page from the active Launchpad mode.
- Kept the previous light show running while browsing other pages; a new mode now takes over only when Start, Play or Enable is pressed.
- Added an explicit Macro lighting enable button and protected background game controls, difficulty and player completion events during page navigation.

## 1.1.0 - 2026-09-10

- Added Easy, Normal and Hard difficulty settings plus automatic game levels.
- Changed Snake to wrap across all four edges and corrected its top-row controls to match the physical `↑ ↓ ← →` icons.
- Slowed Whack-a-Mole, added difficulty-based reaction windows and chances, and reset the timer after each successful hit.
- Added live score, level, high-score and remaining-chances updates to the game panel.

## 1.0.0 - 2026-09-10

- Added model-aware support for the Launchpad family, including 80- and 96-control layouts.
- Added performance and hardware-temperature visualization.
- Added per-pad macros and colors.
- Added video and audio playlists, seeking, playback speed and loop modes.
- Added offline music analysis and low-latency live audio visualization.
- Added automatic detail-parameter persistence, named presets and cross-mode copy/paste.
- Added clock, calendar, weather, focus timer, Snake and Whack-a-Mole utilities.
- Added silent startup, notification-area background service and single-instance behavior.

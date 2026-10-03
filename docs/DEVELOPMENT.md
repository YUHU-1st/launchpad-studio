# Development / 开发与构建

[Project overview / 项目概览](../README.md) · [中文使用指南](GUIDE_ZH.md) · [English user guide](GUIDE_EN.md) · [Feature showcase / 功能预览](SHOWCASE.md)

本页面向源码运行、测试和打包；普通用户请从 [GitHub Releases](https://github.com/YUHU-1st/launchpad-studio/releases/latest) 下载 Windows ZIP 与 Android APK。版本号由根目录 `VERSION` 提供，Android `versionCode` 在 `android/app/build.gradle` 单独维护。

This page covers source runs, testing and packaging. Ordinary users should download the Windows ZIP and Android APK from [GitHub Releases](https://github.com/YUHU-1st/launchpad-studio/releases/latest). The root `VERSION` supplies the release version; Android's `versionCode` is maintained separately in `android/app/build.gradle`.

## Source setup / 源码环境

Windows 源码环境建议 Python 3.12；`setup.ps1` 优先使用已安装的 `uv` 创建 3.12 虚拟环境，否则使用 PATH 中的 `python`。首次安装依赖需要网络。Android 构建需 JDK 17、Android SDK 35、已安装的 `gradle` 和 Android Gradle Plugin 8.7.3；本仓库目前没有 Gradle Wrapper。

Python 3.12 is recommended on Windows. `setup.ps1` uses an installed `uv` to create a Python 3.12 virtual environment, or falls back to `python` on PATH. Initial dependency installation needs network access. Android builds require JDK 17, Android SDK 35, an installed `gradle`, and Android Gradle Plugin 8.7.3; the repository currently has no Gradle Wrapper.

Run from the repository root / 在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe app.py
```

日常无终端启动可双击 `start.bat`、`LaunchpadStudio.vbs` 或 `启动 Launchpad Studio.vbs`；脚本仅在虚拟环境缺失时执行环境准备。`安装桌面快捷方式.bat` 创建源码启动快捷方式。主窗口关闭后常驻托盘，完整退出使用托盘菜单。

For silent everyday source startup, double-click `start.bat`, `LaunchpadStudio.vbs` or `启动 Launchpad Studio.vbs`. The launcher prepares the environment only if it is missing. `安装桌面快捷方式.bat` creates a source-launch shortcut. Closing the main window keeps the process in the tray; use the tray's exit item to shut down fully.

温度 helper 使用 .NET 8；有 .NET SDK 时 `setup.ps1` 可构建它，没有运行时或传感器权限时对应温度可能不可用。VJ 需要 OpenGL 3.3 图形环境。软件运行会创建 `data/settings.json` 和日志，包含真实 PIN、文件路径和宏配置，禁止提交。

The temperature helper targets .NET 8 and can be built by setup when a .NET SDK is installed. Missing runtime, hardware sensors or permissions may leave temperature readings unavailable. VJ needs an OpenGL 3.3 environment. Runtime `data/settings.json` and logs may contain real PINs, paths and macros; never commit them.

## Tests / 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --self-test
node --check remote\app.js
git diff --check
```

单元测试与 MIDI 地址自检不能证明实体灯板、声卡、显示器或 Android 兼容性。测试实机前记录音量、静音、输出设备和布局；测试结束恢复原设置。不得把模拟设备结果写成硬件通过。

Unit tests and MIDI-address self-tests do not establish physical pad, audio-device, monitor or Android compatibility. Record volume, mute, output device and layout before hardware tests, then restore them. Do not describe simulated-device results as hardware passes.

VJ GPU/子进程回归会打开实际预览/全屏窗口并使用可用音频输入；只在适合测试的桌面运行：

The VJ GPU/process smoke test opens real preview/fullscreen windows and uses an available audio input. Run it on a suitable test desktop:

```powershell
.\.venv\Scripts\python.exe tools\vj_smoke.py
```

独立桌面测试实例将配置写入 `build/vj-ui-test-8878/`，十分钟后自行退出。显式 `--virtual-pads` 仅用于标记模拟的路由/界面测试；不是实体灯板验证：

The isolated desktop fixture stores its profile in `build/vj-ui-test-8878/` and exits after ten minutes. `--virtual-pads` explicitly marks a routing/UI simulation, not a physical Launchpad test:

```powershell
.\.venv\Scripts\python.exe tools\vj_desktop_smoke.py --virtual-pads --port=8878
```

在另一个终端运行认证 LAN 回归 / Run authenticated LAN integration in another terminal:

```powershell
.\.venv\Scripts\python.exe tools\vj_remote_smoke.py build\vj-ui-test-8878
```

`tools/vj_rcplus_smoke.mjs`、`tools/rcplus_cdp_eval.mjs` 是开发设备的 WebView/CDP 辅助工具，依赖真实 ADB 连接、调试 APK、端口转发和机器特定地址；先阅读脚本与 [RC Plus 测试记录](RC_PLUS_TESTING.md)，不要把它们当通用一键安装或用户遥控入口。发布 APK 不启用 WebView 调试。音频关闭顺序必须保持停止流、等待读取线程结束、再释放原生音频对象。

`tools/vj_rcplus_smoke.mjs` and `tools/rcplus_cdp_eval.mjs` are development-device WebView/CDP helpers requiring real ADB access, a debug APK, forwarding and machine-specific addresses. Read the scripts and [RC Plus testing notes](RC_PLUS_TESTING.md) first; they are not general installation or user-remote commands. Release APKs do not enable WebView debugging. Audio shutdown must stop the stream, wait for its reading worker, then release native audio objects.

## Build packages / 构建安装包

Only Windows / 仅构建 Windows：

```powershell
.\build_exe.bat
```

产物在 `dist/LaunchpadStudio/`，需完整分发目录。统一双端发布脚本会执行测试、Windows 打包/打包自检、Android release/lint、APK 对齐签名验证及 SHA-256：

Distribute the complete `dist/LaunchpadStudio/` directory. The unified release script runs tests, Windows packaging and packaged self-test, Android release/lint, APK alignment/signature verification, and SHA-256 generation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

产物 / Outputs:

```text
release/LaunchpadStudio-<version>-windows-x64.zip
release/LaunchpadStudioRemote-<version>-android.apk
release/SHA256SUMS.txt
```

该脚本需 Node.js、Gradle、Android SDK Build Tools，并使用现有 `%USERPROFILE%\.android\debug.keystore` 的 `androiddebugkey` 签名。不要重新生成/公开个人密钥或称其为 Play 商店签名流程；客户端覆盖更新依赖签名一致。脚本不发布 GitHub Release，构建成功也不代表实机回归已经完成。

The script needs Node.js, Gradle and Android SDK Build Tools. It currently signs using the existing `%USERPROFILE%\.android\debug.keystore` / `androiddebugkey`. Do not replace or publish personal signing keys, or describe this as a Play Store signing workflow; in-place APK updates need matching signatures. The script does not publish GitHub Releases, and a successful build does not replace hardware regression.

Independent Android debug build / 单独构建 Android 调试版：

```powershell
gradle -p android assembleDebug
```

SDK 定位可用 `ANDROID_HOME`；JDK 定位可用 `JAVA_HOME`。Android 目标为 API 35，最低 API 26，仍须保持 Android 10 / API 29 的 Java 和 WebView 兼容性。

Use `ANDROID_HOME` for the SDK and `JAVA_HOME` for the JDK when needed. Android targets API 35 with minimum API 26; preserve Java/WebView compatibility with Android 10 / API 29.

## Project map / 目录说明

| Path | Purpose / 用途 |
| --- | --- |
| `app.py` | Desktop Tk interface, mode lifecycle, routing, tray and remote command integration / 桌面界面、模式切换、路由、托盘与遥控集成。 |
| `core/launchpad.py`, `midi_winmm.py`, `multi_launchpad.py` | MIDI transport, model profiles and extended/mirror/independent routing / MIDI、型号配置、多板联动。 |
| `core/audio_engine.py`, `video_engine.py` | File players and reactive audio/video LED rendering / 音视频文件播放器、拾音与灯效。 |
| `core/vj_engine.py`, `vj_output.py`, `vj_shaders.py` | Live audio features, native LED renderer and isolated GPU windows / 实时特征、原生灯效、GPU 输出进程。 |
| `core/performance.py`, `temperature.py`, `macros.py`, `miniapps.py`, `rhythm.py`, `weather.py`, `settings.py` | Monitoring, actions, tools/games, weather and persistence / 监控、宏、工具游戏、天气与配置。 |
| `core/remote.py`, `windows_media.py`, `remote/` | PIN-protected LAN service, Windows media/audio bridge and touch web UI / PIN 遥控服务、系统媒体音频桥接、触控网页。 |
| `android/` | Native connection shell and desktop-hosted WebView; not a standalone MIDI engine / 原生配对壳与 WebView，非独立 MIDI 引擎。 |
| `tests/`, `.github/workflows/` | Python tests and Windows/Android CI / 测试与持续集成。 |
| `tools/TemperatureHelper/` | Isolated .NET/LibreHardwareMonitor sensor reader / 隔离运行的温度采集工具。 |
| `tools/capture_media.py`, `tools/vj_render_demo.py`, `tools/vj_led_demo.py`, `tools/docs_preview.py`, `tools/docs_media.py` | Documentation UI and actual-renderer media helpers; use sample/simulated input and label outputs accurately / 文档界面、截图导览与渲染器素材工具，样例与模拟输入应明确标注。 |
| `docs/`, `docs/media/` | Bilingual guides, showcase, release/test history and public sample media / 双语文档、功能预览、历史记录及公开样例。 |
| `build/`, `dist/`, `release/`, `android/app/build/`, `.venv/`, `data/` | Generated outputs or private runtime state; not source to commit / 构建产物或私有状态，不应提交。 |

## Documentation and release discipline / 文档与发布规范

`tools/docs_preview.py` 打开隔离的当前界面，使用模拟 X/MK2、示例宏/预设/媒体与开发电脑真实性能读数，不枚举真实 MIDI 或控制用户播放器。它将随机 PIN 与配置写入临时 `build/docs-preview-*/`，遥控端口为 8879，一小时后自动退出。截图须避开配对 PIN 和个人路径。保存当前截图后，`tools/docs_media.py` 使用 Pillow 与 PATH 上的 FFmpeg 生成双语字幕导览和手机拼图；不要把这些幻灯片称为实机录像。

`tools/docs_preview.py` opens an isolated current UI with virtual X/MK2 pads, sample macros/presets/media, and real development-PC metrics. It does not enumerate real MIDI or control personal players. Its random PIN/configuration stay in a temporary `build/docs-preview-*/` profile, using port 8879 with a one-hour automatic exit. Exclude pairing PINs and personal paths from captures. After saving screenshots, `tools/docs_media.py` uses Pillow and FFmpeg on PATH to produce captioned walkthroughs and the mobile contact sheet; these are slides, not hardware recordings.

```powershell
.\.venv\Scripts\python.exe tools\docs_preview.py
# Capture the displayed UI first / 先截取实际界面
.\.venv\Scripts\python.exe tools\docs_media.py
```

维护 [中文指南](GUIDE_ZH.md)、[English guide](GUIDE_EN.md)、[功能预览](SHOWCASE.md)、[VJ 说明](VJ.md) 和根 README 的一致性。演示注明实际界面、样例数值、虚拟灯板或模拟节拍，不能把文档幻灯片称为硬件录制。新增素材必须避免泄露 PIN、绝对个人路径、媒体版权内容与调试日志。

Keep the [Chinese guide](GUIDE_ZH.md), [English guide](GUIDE_EN.md), [showcase](SHOWCASE.md), [VJ notes](VJ.md) and root README consistent. Identify real UI, sample data, virtual pads and simulated beats. Documentation slides are not hardware footage. Avoid exposing PINs, private absolute paths, copyrighted media content and debug logs.

`CODEX_HANDOFF.md`、`CODEX_CONTINUE_PROMPT.md`、`REMOTE_ANDROID_REQUIREMENTS.md` 和 `RC_PLUS_TESTING.md` 含历史环境与阶段状态，部分段落早于当前版本；它们用于追溯，不能当作当前安装步骤、设备可用性或最终发布状态。当前源码/`VERSION`、当前 Release 与明确标注日期的验证证据优先。修改前仍须遵守根 `AGENTS.md`，检查未提交内容并保留用户改动。

`CODEX_HANDOFF.md`, `CODEX_CONTINUE_PROMPT.md`, `REMOTE_ANDROID_REQUIREMENTS.md` and `RC_PLUS_TESTING.md` retain historical environments and milestones. Some sections predate the current release; do not treat them as current installation instructions, device availability or final release status. Prefer current source/`VERSION`, actual Releases and dated verification evidence. Follow the root `AGENTS.md`, inspect dirty state before changes, and preserve user work.

# Launchpad Studio 2.3 · Pulse Canvas

把 Novation Launchpad 变成性能仪表、宏键盘、音乐与视频灯板、游戏机，以及与舞台大屏联动的 VJ 控制中心。

Turn your Novation Launchpad into a PC dashboard, macro pad, music/pixel-video visualizer, LED game board, and audio-reactive VJ companion.

[![Latest release](https://img.shields.io/github/v/release/YUHU-1st/launchpad-studio)](https://github.com/YUHU-1st/launchpad-studio/releases/latest)
[![Windows tests](https://github.com/YUHU-1st/launchpad-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/YUHU-1st/launchpad-studio/actions/workflows/ci.yml)
[![Android build](https://github.com/YUHU-1st/launchpad-studio/actions/workflows/android.yml/badge.svg)](https://github.com/YUHU-1st/launchpad-studio/actions/workflows/android.yml)

[下载 / Download](https://github.com/YUHU-1st/launchpad-studio/releases/latest) · [中文使用手册](docs/GUIDE_ZH.md) · [English guide](docs/GUIDE_EN.md) · [截图与视频 / Gallery](docs/SHOWCASE.md) · [更新记录 / Changelog](CHANGELOG.md)

[![2.3 桌面界面与两块模拟灯板 / Current desktop with two simulated pads](docs/media/performance-2.3.jpg)](docs/SHOWCASE.md)

*新版真实界面，灯板为模拟设备；点击图片进入完整演示库。Current UI with explicitly simulated pads; click for the complete gallery.*

## 它能做什么 / What can it do?

一个 Windows 桌面程序，八个一级页面；单板直接使用，多板可以扩展、复制或运行不同功能，Android / 手机浏览器通过局域网遥控非游戏功能。

One Windows application, eight main pages. Use one pad or link several in Extended, Mirror, or Independent mode; control non-game features from Android or a mobile browser on your LAN.

| 功能 / Feature | 可以做什么 / What you get | 预览 / Preview |
| --- | --- | --- |
| 性能与温度 / Performance | CPU、内存、GPU、磁盘空间、吞吐量与可用温度传感器 → LED 仪表 / Live metrics and available temperatures | [视频 / Video](docs/media/performance-demo.mp4) |
| 宏按键 / Macros | 热键、文字、程序、网址、媒体键、鼠标与组合动作；可与非游戏灯效并行 / Pad actions alongside lighting | [视频 / Video](docs/media/macros-demo.mp4) |
| 视频像素播放器 / Pixel video | 播放列表、拖动进度、变速、循环与六种滤镜 / Playlists, seeking, speed, loops and filters | [视频 / Video](docs/media/video-player-demo.mp4) |
| 音乐演示 / Music show | 文件播放与分析，十种灯效及频谱、响度、门限参数 / File playback, analysis and adjustable visualizers | [视频 / Video](docs/media/music-show-demo.mp4) |
| 实时拾音 / Live audio | 麦克风或 Windows 系统回放，无需导入音乐 / Microphone or system loopback with live lighting | [视频 / Video](docs/media/live-audio-demo.mp4) |
| VJ 投屏 / VJ projection | 八种 GPU 场景、自动换景、多显示器、小窗口及 Alpha / Scenes, sequencing, multi-display, preview and alpha | [视频 / Video](docs/media/vj-demo.mp4) |
| 原生 VJ 灯板 / Native VJ LEDs | 十二种高对比像素/线条灯效；独立图形、共享节拍和配色 / Independent graphics, shared beat/palette | [视频 / Video](docs/media/vj-led-demo.mp4) |
| 桌面工具 / Utilities | 时钟、日历、天气、专注计时器 / Clock, calendar, weather and focus | [视频 / Video](docs/media/desktop-utilities-demo.mp4) |
| 解压游戏 / Casual games | 穿墙贪吃蛇、打地鼠、难度/关卡与得分光效 / Wraparound Snake, Mole, stages and score effects | [贪吃蛇 / Snake](docs/media/snake-demo.mp4) · [打地鼠 / Mole](docs/media/whack-a-mole-demo.mp4) |
| 自动谱面音游 / Rhythm games | 瀑布与环形音游，音乐生成谱面，难度/速度/键数可调 / Auto-charts with adjustable difficulty/speed/lanes | [瀑布 / Waterfall](docs/media/waterfall-demo.mp4) · [环形 / Radial](docs/media/radial-rhythm-demo.mp4) |
| 多板布局 / Multi-pad layout | 拖动、编号辨认、原生拼接预览与独立功能路由 / Drag layouts, identify devices, preview native canvas | [图文与视频 / Walkthrough](docs/SHOWCASE.md#layout) |
| 手机与系统媒体 / Mobile & media | PIN 配对、布局/VJ/预设，媒体会话、歌词、音量和输出切换 / LAN control, lyrics and audio outputs | [图文与视频 / Walkthrough](docs/SHOWCASE.md#remote) |

设置自动记忆；音乐、拾音和视频支持命名预设、最近使用、恢复默认与桌面跨模式复制兼容参数。关闭主窗口收起到托盘，演示继续；顶部“全部停止并熄灯”立即结束所有输出。

Settings persist. Music/live/video have named and recent presets, desktop defaults and compatible-parameter copy/paste. Closing the main window keeps the app in the tray; Stop All / Blackout ends every output.

## 三分钟开始 / Quick start

1. **下载并解压 / Download and extract.** 从 [Releases](https://github.com/YUHU-1st/launchpad-studio/releases/latest) 下载 `LaunchpadStudio-*-windows-x64.zip`，完整解压后运行 `LaunchpadStudio.exe`，无需 Python。Download the Windows ZIP, extract all files, then run the executable; do not run inside the archive.
2. **连接 / Connect.** USB 连接 Launchpad，关闭可能占用 MIDI 端口的软件；进入“布局设置”→“扫描并连接全部 Launchpad”。Release competing MIDI applications, then open Layout Settings → Scan and Connect.
3. **开始 / Start.** 第一次建议“性能监控”→“开始实时监控”；视频/音乐先在电脑端添加文件。Try Performance → Start, or import media on the PC before playing it.
4. **调整 / Adjust.** 用左侧配色、亮度和模式细节调整效果；浏览页面不停止演示，点击新模式的开始按钮才接替输出。Adjust palette/brightness and mode settings; browsing pages does not interrupt playback.

[完整安装、升级、配对及排错 / Setup and troubleshooting](docs/GUIDE_ZH.md#安装与首次使用) · [English instructions](docs/GUIDE_EN.md#install-start-and-update)

## 多板像多显示器一样排列 / Arrange pads like monitors

[![新版布局设置，模拟双板 / Current layout settings with simulated pads](docs/media/layout-2.3.jpg)](docs/SHOWCASE.md#layout)

| 联动方式 / Link mode | 使用逻辑 / How it works |
| --- | --- |
| 扩展 / Extended | 两块横排 16×8、竖排 8×16；工具和游戏扩大活动区域，不拉伸原来的方形 / Grow the native canvas/game area instead of stretching an 8×8 image |
| 复制 / Mirror | 每块显示同一画面，普通模式页面统一启动与切换 / Show the same frame on every pad, controlled from one mode page |
| 独立 / Independent | 布局页分配设备功能，再开始相应模式；同一功能共享引擎和参数 / Assign functions per device; devices using the same function share its engine/settings |

所有模式保留完整拼接预览，可拖动板块移动或交换位置；“在实机显示编号”用数字灯光辨认设备，手机端也能调整布局。

Every mode retains the composite LED preview. Drag tiles to move/swap them, identify devices with illuminated numbers, and manage the same layout from mobile.

## 大屏与灯板各司其职 / Separate screen and pad visuals

[![八种 GPU VJ 场景 / Eight GPU VJ scenes](docs/media/vj-styles.png)](docs/media/vj-demo.mp4)

[![十二种原生高对比 LED 风格 / Twelve native high-contrast LED styles](docs/media/vj-led-styles.png)](docs/media/vj-led-demo.mp4)

分别多选显示器与灯板：大屏保持视频分辨率，灯板自动匹配所选设备的原生布局；两者共享节拍、估计情绪和配色，图形、速度、强度与密度独立。支持仅投屏、仅原生灯板或同时输出，未选灯板可保留其他模式。

Select screens and pads separately. Screens retain their video resolution; pads use the selected native layout. Graphics, motion and detail can differ while sharing audio features and palette. Screen-only, native-LED-only and combined output are available.

[VJ 设置与现场限制 / VJ guide](docs/VJ.md) · [独立投屏/灯板演示 / Independent-output demo](docs/media/vj-led-demo.mp4)

## 手机遥控 / Control from your phone

![手机版 Studio 与布局页，浏览器预览和模拟灯板 / Mobile Studio and Layout, browser preview with simulated pads](docs/media/remote-overview-2.3.jpg)

同一局域网 → 桌面顶部“手机遥控”查看地址和六位 PIN → 安装 Release 的 Android APK，或用手机浏览器打开该地址。可调整非游戏功能、布局、VJ 与预设，以及兼容 Windows 播放器的播放/暂停、进度、封面、同步歌词、系统音量/静音和默认音频输出。

Use the same LAN → open the PC's Mobile Remote dialog for its address and PIN → install the APK or visit the address in a browser. Control non-game modes, layout, VJ, presets, compatible Windows media sessions, lyrics and audio settings.

电脑端必须保持运行，文件在电脑导入；手机不上传文件、不接收电脑音频，游戏不开放手机控制。只用于可信局域网，不要把遥控端口暴露到公网。

The PC remains the host. Import files there; mobile file upload, PC-audio streaming and mobile game control are not provided. Keep the PIN-protected HTTP service on a trusted LAN, not the public Internet.

## 支持范围与须知 / Compatibility and expectations

- **平台 / Platforms:** Windows x64；Android 8.0+ 遥控，DJI RC Plus Android 10 有回归记录。当前软件界面为中文，文档中英双语。The current application UI is Chinese; documentation is bilingual.
- **灯板 / Pads:** Original/MK1、S、Mini MK1/MK2/MK3、MK2、X、Pro、Pro MK3；旧款红绿设备映射为可用颜色。Nine profiles, with legacy supported-color mapping; not every profile has been physically tested.
- **传感器 / Sensors:** GPU 占用当前依赖 NVIDIA `nvidia-smi`；温度取决于硬件、权限和 .NET 8 辅助程序，不伪造读数。GPU usage currently relies on NVIDIA; available temperature readings vary.
- **媒体 / Media:** 视频模式不播放视频音轨，音乐变速会改变音高，外部播放器进度/循环能力取决于其 Windows 媒体接口。Pixel video has no soundtrack playback; speed changes pitch; external-player capabilities vary.
- **VJ / Stage:** OpenGL 3.3；帧率取决于硬件，音乐风格/情绪是启发式估计，普通 HDMI/DP 不传递独立 Alpha，本版无 Spout/NDI/DMX。See the VJ guide for stage and transparency limits.
- **验证 / Evidence:** 2.3 经 GPU、打包程序和 RC Plus 回归；本次多板使用模拟设备，新的实体多板及多实体显示器回归仍需现场验证。Preview media is labeled, not presented as physical stage footage.

## 文档导航 / Documentation

| 想做什么 / Goal | 去哪里 / Read |
| --- | --- |
| 安装、连接、逐项使用 / Get started | [中文手册](docs/GUIDE_ZH.md) · [English guide](docs/GUIDE_EN.md) |
| 看每个功能的截图、独立视频与流程 / Explore every feature | [完整演示库 / Complete gallery](docs/SHOWCASE.md) |
| VJ 多目标、Alpha 与现场设置 / Stage setup | [VJ 专项指南 / VJ guide](docs/VJ.md) |
| 源码运行、测试、打包 / Develop and build | [开发指南 / Development](docs/DEVELOPMENT.md) |
| 版本变化 / Release history | [Changelog](CHANGELOG.md) · [2.3 release notes](docs/RELEASE_2.3.0.md) |
| 测试与历史交接 / Tests and archive | [文档索引 / Docs index](docs/README.md) |

独立项目，与 Novation 无隶属或背书关系；Launchpad 属于相应商标权利人。第三方依赖说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

An independent project, not affiliated with or endorsed by Novation. Launchpad belongs to its trademark holder; see the dependency notices for attribution.

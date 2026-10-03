# Launchpad Studio 2.3 · Pulse Canvas

## 中文

新增 12 种专为 Launchpad 原生网格设计的高对比像素、线条与节拍图形，黑底亮色，不再默认缩小投屏视频。
灯板和屏幕的图形、速度、强度、密度分别控制，共用音频节拍、情绪估计和色彩主题；可选原画采样。

显示器和 Launchpad 都可多选。灯板自动按所选设备的真实布局使用 8×8、16×8、8×16 等原生分辨率，屏幕宽高不受影响。
未选灯板保持原模式，支持仅灯板、仅投屏或同时输出；统一布局中启动其他灯板模式不再关闭投屏。
Android 同步提供所有选项，并修复了手机网页小文件在 Windows 原生传输路径上的超时问题。

Windows ZIP 解压运行 `LaunchpadStudio.exe`，Android APK 可覆盖更新。
[使用说明与验证范围](VJ.md) · [12 种灯板光效与独立投屏演示](media/vj-led-demo.mp4)

本次验证使用真实 GPU 和 RC Plus，以及两块明确标注的模拟灯板；开发时没有连接实体 Launchpad，因此本次不能宣称已完成新的多板灯光实机回归。
只有一个实体电脑显示器，现场多实体大屏仍需彩排。普通 HDMI 不传输独立 Alpha，风格和情绪仍为启发式估计。

## English

Twelve native high-contrast pixel/line/beat patterns render directly on Launchpad grids. Screen and pad visuals have independent style, speed, intensity and density, with shared music analysis, palette and estimated mood. Original GPU image sampling remains optional.

Multi-select monitors and pad devices. Native LED size follows the selected layout without modifying screen resolution; unselected pads retain their mode. LED-only output is supported, and starting another LED mode in unified layouts keeps the projection running. Android exposes matching controls. Small mobile UI assets avoid the Windows native-transfer timeout observed during testing.

Run the Windows ZIP without Python or update the Android APK. See [setup and verified scope](VJ.md) and the [twelve-style native LED / independent-screen demo](media/vj-led-demo.mp4).

This update was tested on the actual GPU and RC Plus with explicitly simulated pad devices; no physical Launchpad was connected, so this is not a new multi-pad hardware regression. Only one physical PC display was available. Rehearse with venue screens. Standard HDMI does not carry separate alpha; music descriptors remain heuristic.

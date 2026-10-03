# Launchpad Studio 2.2 · Stage VJ

## 中文

新增音乐实时驱动的 GPU VJ 背景，8 种原创程序化画面可自动编排或手动选择。
支持系统声音/麦克风、节拍和频谱响应、启发式风格/情绪估计、自动/指定配色及细节参数记忆。

独立全屏输出支持多选显示器及小窗口预览；画幅、分辨率和帧率可选，Alpha 提供真正透明窗口。
普通 HDMI 不传输透明通道，不包含 Spout/NDI 或透明文件导出。灯板映射使用实际 GPU 图像，并适配 Matrix 多板布局。
Android 与手机网页具有对应控制，并修正了实时状态刷新导致输出选项草稿被覆盖的问题。

Windows 包解压运行 `LaunchpadStudio.exe`，不需要 Python；Android APK 可覆盖安装旧版。
使用 GPU VJ 需要支持 OpenGL 3.3 的显卡驱动。当前实测只有一个实体显示器，多块实体大屏的同时投放仍需现场彩排。
完整操作说明与验证范围见 [VJ.md](VJ.md)，演示视频为实际着色器配合明确标注的模拟节拍生成。

## English

Real-time audio-driven GPU VJ backgrounds add eight original procedural styles, automatic sequencing,
system/microphone capture, beat/spectrum response, heuristic music descriptors, palettes and remembered parameters.

Choose multiple fullscreen display targets and/or a preview window, custom aspect/resolution/FPS, and genuine RGBA transparent windows.
Normal HDMI does not carry alpha; Spout/NDI and alpha-file export are not included.
Optional LED mapping downsamples the actual GPU image through the multi-Launchpad Matrix layouts.
Android/mobile web expose corresponding controls and preserve unsaved output edits during live state refresh.

The Windows ZIP runs without Python and the APK updates the existing Android client.
VJ requires OpenGL 3.3. Only one physical PC display was available for testing; multi-physical-screen output needs venue validation.
See [VJ.md](VJ.md) for setup and verified scope. Demo media renders production shaders with labeled simulated beats.

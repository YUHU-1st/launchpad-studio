# Launchpad Studio 2.3 · Pulse Canvas VJ

## 中文

### 使用

打开“实时 VJ”，选择音乐实际输出的 WASAPI 系统声音设备，或麦克风。
选择自动编排或一种固定画面风格，配色可自动估计、使用色彩主题或自定义主色。
画幅控制图像比例，宽高控制真正的 GPU 渲染分辨率，FPS 控制目标输出帧率。
选择 1280/1920/2560/3840/7680 等常用宽度会按画幅自动计算高度，也可以手动输入。
最大宽高为 7680×4320；高分辨率与多个窗口会增加 GPU 负载，未保证所有硬件达到目标帧率。

“投屏目标”可多选，电脑必须在 Windows 中把对应显示器设为可用的扩展桌面。
每个选中的屏幕有独立全屏窗口，同一画面可以同时投到多台屏幕；小窗口预览可以单独运行或同时打开。
画面保持原始比例，目标屏幕比例不同时留边，不拉伸。不支持单个视频横跨多块电脑显示器的拼接。
F11/双击切换全屏；Esc 关闭当前窗口。关闭最后一个输出窗口时，音频采集和灯板映射一起停止。
透明的小窗口没有边框，可按住画面拖动。主界面收起到托盘不会关闭 VJ。

勾选“启用 Launchpad 原生 VJ 灯效”，并多选灯板目标。默认“自动联动”按屏幕场景选择相应的像素风格，也可以固定选择 12 种高对比图形。
屏幕和灯板使用同一个实时音频分析器、配色与节拍包络，但图形、速度、强度、密度分别控制。灯板是真正黑底的原生像素，没有缩小高清视频时的模糊和泛光。
灯板画布按所选已连接设备的相对位置自动计算：一块 8×8，两块横排 16×8、竖排 8×16；复制模式每块 8×8。布局间隙保留，独立布局中明确选中的多块灯板也使用其原生拼接画布。未选设备不受 VJ 帧影响，继续原模式。
灯板输出最高约 20 FPS，与屏幕分辨率和输出帧率分离。切换目标或拖动布局会自动调整灯板原生尺寸，绝不修改屏幕的宽高。
只要选择了原生灯效，就可以取消全部显示器和预览，仅运行灯板；“原画采样”使用真实 GPU 图像下采样，需至少打开预览或投屏。
关闭灯板输出会释放目标设备并恢复其仍在运行的原模式；在统一布局中开始另一灯板模式时只接替 LED，现有 VJ 投屏继续运行。独立布局中的未选设备可同时使用其他模式；只是浏览页面不会打断。
“全部停止并熄灯”停止所有音频/视频/VJ 和灯板输出。

### 音频参数

- 灵敏度：整体音频响应倍数。
- 静音阈值：低于此 RMS 电平的声音不触发能量与节拍。
- 运动速度：改变画面运动速率，不改变音频播放速度。
- 光效强度：画面亮度/辉光，不改变 Launchpad 全局亮度。
- 图形密度：细节与重复图形密度。
- 自动换景秒数：自动编排场景持续时间，场景之间有约 1.5 秒过渡。
- 灯板速度、强度、密度：仅调整原生 LED 图形，不改变投屏画面。
- 灯板对比度、亮度截断：提高亮暗分离，低于截断值的像素为黑色。

BPM 是滑动窗口包络自相关估计，风格与情绪由节拍、频谱重心、低频和能量启发式判断。
静音时不输出虚构 BPM；音乐切换后的节奏锁定需要数秒，半拍/倍拍及非规则音乐可能产生估计误差。
支持任意播放器的系统回放，不需要导入文件。手机端的“应用输出设置”统一提交宽高、显示器和开关，其余风格/音频参数实时生效。

### Alpha 与现场边界

Alpha 使用真正的预乘 RGBA 缓冲，不是仅把背景涂黑。透明窗口允许看到下层桌面与窗口。
普通 HDMI/DisplayPort 屏幕输出在 Windows 合成之后显示，不保留独立 Alpha；不能凭此直接向混合台输出透明通道。
本版没有 Spout/NDI、投影网格扭曲、灯光 DMX 控制或透明视频导出。使用前请在现场的实际 GPU、屏幕分辨率及透明捕获工具上彩排。
快速闪光可能影响光敏人群；现场使用前降低强度并做风险评估。

## English

Select the actual system playback endpoint or a microphone on the VJ page. Choose automatic sequencing or one of eight original styles, then set aspect, true rendering resolution and target FPS. Select any number of available extended-desktop monitors, with or without a small preview. Each screen shows the same complete image, aspect-preserved with letterboxing; this is not a single image spanning multiple PC screens.

F11/double-click toggles fullscreen; Esc closes one output. Closing the last output stops capture and LED mapping. Transparent preview windows can be dragged. Tray minimization of the main application does not stop VJ.

Select any connected pad targets and enable native LED output. Twelve hard-edged, high-contrast pixel styles render at native resolution on black, without shrinking a video. Screen and pad graphics/speed/intensity/density are independent but share one audio analyzer, palette, beat envelope and mood estimate. Contrast and cutoff improve LED separation.

One pad is 8×8, two horizontal pads 16×8, and two vertical pads 8×16; mirrors remain 8×8 per unit, and layout gaps are preserved. The selected-pad canvas follows layout changes without modifying screen resolution. Explicitly selected pads in Independent layouts also use their native composite coordinates; unselected pads retain their mode. LED-only output works without any preview/display windows. Original Image Sampling is optional and requires a screen or preview output.

Disabling LED output releases its targets and restores any still-running previous modes. Starting another LED mode in unified layouts replaces LED ownership but leaves the VJ projection running. Merely browsing pages does not interrupt anything. Stop All / Blackout stops all outputs. Android has the same target selectors, parameters and separate resolution readouts.

Adjust sensitivity, RMS silence gate, visual speed, intensity, density and automatic scene interval. Settings persist; Android exposes the same controls. Tempo is a rolling-envelope autocorrelation estimate; genre/mood descriptions are spectral/energy heuristics, not guaranteed classification. Silence has no fictitious BPM. Tempo takes seconds to settle and may have half/double-time ambiguity.

Alpha is genuine premultiplied RGBA, composited over the Windows desktop. HDMI/DisplayPort normally carries the final opaque composition, not a separate alpha channel. Transparent external composition needs a capture/mixing tool that preserves transparency. There is no Spout, NDI, projection mesh warping, DMX or alpha-video export in this release. OpenGL 3.3 is required. Maximum configured size is 7680×4320; actual FPS depends on GPU and output count. Rehearse with the venue hardware and consider photosensitivity risks.

## Verification / 验证

Production shaders were rendered on the actual NVIDIA RTX 5080 Laptop GPU across all eight styles, opaque and premultiplied-alpha buffers. Streaming analysis was tested with silence and simulated 120 BPM pulses. GPU/process tests cover style changes, 60 FPS target, alpha window rebuilds, concurrent preview/fullscreen windows, audio-device changes, native horizontal/vertical LED shapes and safe shutdown.

Desktop/LAN integration covers parallel performance/VJ operation, mapped Launchpad X colors, browsing-page continuity, explicit mode changes and blackout. DJI RC Plus Android 10 / WebView 95 was tested over LAN for VJ start/stop, target selection, alpha changes, edit preservation during state updates and reconnect. Windows executable packaging and Android build/lint/signatures are checked separately.

The 2.3 update adds tests for all twelve native LED styles, target subsets, horizontal/vertical/mirror dimensions, unselected-pad isolation, unchanged screen resolution, LED-only operation and legacy settings migration. RC Plus tests use two explicitly simulated pad devices because no physical Launchpad was connected for this update; this is not a new hardware regression result. The prior 2.2 physical-device result above is historical. Small mobile UI assets now use ordinary HTTP response bodies rather than Windows native sendfile, after LAN page transfers produced WinError 121 timeouts while JSON requests still worked.

Only one physical computer monitor is connected during development. Concurrent preview/fullscreen windows were tested on that monitor; simultaneous output across two or more physical monitors still requires venue hardware testing. Demo media uses production shaders with labeled simulated music features and is not a recording of genre-recognition accuracy.

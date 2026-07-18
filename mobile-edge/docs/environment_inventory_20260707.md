# 环境库存记录

日期：2026-07-07  
目录：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab`

## 1. 本机已有能力

| 类别 | 状态 | 说明 |
|---|---|---|
| Git | 已有 | `git version 2.51.0.windows.1` |
| GitHub CLI | 已有并已登录 | `gh version 2.92.0`，用于拉 GitHub 参考仓库 |
| Python | 已有 | Python 3.11.9，项目独立 venv 在 `env\py311` |
| Node.js / npm | 已有 | Node v24.11.0，npm 11.6.1 |
| Java | 已有 | Java 21 LTS；项目环境优先使用 Microsoft OpenJDK 17 |
| Gradle | 已有 | 系统已有 Gradle |
| ffmpeg | 已有 | ffmpeg 8.1.1 |
| Docker | 已有 | Docker 29.6.1 |
| Rust | 已有 | rustc/cargo 1.95.0 |
| GPU | 已有 | RTX 2080 Ti 11GB，NVIDIA-SMI 610.47，CUDA UMD 13.3 |

## 2. 项目内已安装工具

| 工具 | 路径 | 用途 |
|---|---|---|
| ADB / platform-tools | `tools\platform-tools\platform-tools\adb.exe` | 手机授权、设备发现、scrcpy 底层连接 |
| scrcpy 4.0 | `tools\scrcpy\scrcpy-win64-v4.0\scrcpy.exe` | Phase 0 手机屏幕流验证 |
| Android command line tools | `tools\android-sdk\cmdline-tools\latest` | 构建 Android 原型 |
| Android SDK Platform | `tools\android-sdk\platforms\android-36`、`tools\android-sdk\platforms\android-37.0` | Android App 编译目标 |
| Android Build Tools | `tools\android-sdk\build-tools\36.0.0`、`tools\android-sdk\build-tools\37.0.0` | aapt2 / d8 / apksigner 等 |
| Android NDK | `tools\android-sdk\ndk\29.0.14206865` | ScreenStream/WebRTC 等源码构建需要 |
| Microsoft OpenJDK 17 | `C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot` | Android/Gradle toolchain 构建需要 |
| Python venv | `env\py311` | 实时服务、OCR、ASR、事件处理 |

## 2.1 已构建 APK

| APK | 路径 | 状态 |
|---|---|---|
| ScreenStream 4.4.1 FDroid Debug | `downloads\apk\ScreenStream-4.4.1-FDroid-debug-built.apk` | 已从本地源码构建，APK v2 签名验证通过 |

## 3. Python 能力

已安装的关键能力：

- 实时服务：`fastapi`、`uvicorn`、`websockets`
- 图像/视频处理：`opencv-python`、`numpy`、`pillow`、`imagehash`
- OCR：`onnxruntime`、`rapidocr-onnxruntime`
- ASR 基础：`vosk`、`soundfile`、`faster-whisper`
- WebRTC/视频容器：`aiortc`、`av`
- 本地数据/事件：`duckdb`、`orjson`、`pydantic`
- 工具链：`httpx`、`rich`、`typer`、`mss`、`psutil`

暂缓：

- Whisper/Vosk 具体模型权重：暂不下载，等音频采集路线确认后再选中文/英文/多语模型。
- `torch` / `transformers` / 大型 VLM 权重：暂不装，避免未确定实验路线前占用大量磁盘和显存。

## 4. 第三方参考仓库

| 分类 | 仓库 | 本地路径 | 获取方式 | 用途 |
|---|---|---|---|---|
| 手机屏幕流 | ScreenStream | `third_party\phone-screen\screenstream` | git shallow clone | MediaProjection + MJPEG/WebRTC/RTSP 参考 |
| 手机屏幕流 | OpenTok screenshare sample | `third_party\phone-screen\opentok-screenshare-android-sample` | git shallow clone | Android MediaProjection + WebRTC 示例 |
| 手机屏幕流 | LiveKit Android SDK | `third_party\phone-screen\livekit-client-sdk-android` | git shallow clone | 正式 App 互联/屏幕共享 SDK 参考 |
| 屏幕记忆 | screenpipe | `third_party\screen-memory\screenpipe` | git shallow clone | 本地优先时间线/屏幕记忆参考 |
| 屏幕记忆 | Omi | `third_party\screen-memory\omi` | gh sparse clone | 屏幕+对话+可穿戴记忆生态参考 |
| 屏幕记忆 | Windrecorder | `third_party\screen-memory\Windrecorder` | GitHub zip | 本地屏幕记录/OCR/时间线参考 |
| 实时 VLM | NVIDIA Live VLM WebUI | `third_party\realtime-vlm\live-vlm-webui` | git shallow clone | PC 端实时 VLM 实验基座 |
| 实时 VLM | Vinci | `third_party\realtime-vlm\Vinci` | git blobless clone | 第一视角实时视频语言助手参考 |
| 实时 VLM | Egocentric procedural AI assistant | `third_party\realtime-vlm\Building-Egocentric-Procedural-AI-Assistant` | git blobless clone | 第一视角过程助手研究地图 |
| 眼镜 | OpenVision | `third_party\glasses\OpenVision` | git shallow clone | Meta Ray-Ban + 手机 App + AI 参考 |
| 眼镜 | VisionClaw | `third_party\glasses\VisionClaw` | GitHub zip | 眼镜第一视角 + 手机 + 实时 AI 参考 |
| 学习助手 | edX learning-assistant | `third_party\learning-assistant\edx-learning-assistant` | git shallow clone | 正式学习平台 AI 助手参考 |
| 学习助手 | DeepTutor | `third_party\learning-assistant\DeepTutor` | git blobless clone | AI tutor / RAG / 学习路径参考 |

## 5. 当前可进入的实验阶段

现在已经具备：

1. USB 授权后用 ADB / scrcpy 验证真实手机屏幕流。
2. 安装本地构建的 ScreenStream APK，验证 MediaProjection 屏幕流输出。
3. 用 Python 服务接收帧、抽帧、OCR、ASR、WebRTC、事件记录。
4. 用 Android SDK 构建后续 MediaProjection 原生 App 原型。
5. 用第二台手机/运动相机模拟第一视角流。
6. 后续在 PC 上尝试 Live VLM / Vinci 类实时理解基座。

仍需硬件到位后验证：

1. 华为手机 ADB 授权是否稳定。
2. 手机系统音频是否允许捕获。
3. 短视频 App 是否出现 `FLAG_SECURE` 或音频拒绝捕获。
4. Wi-Fi ADB 在真实网络下的延迟和稳定性。
5. 第一视角流与手机屏幕流的时间同步误差。

# HuaweiCup Phone Capture Lab

用途：为华为杯项目的“手机当前浏览内容直接采集、PC边缘分析、停留分段、轻量回传”做独立实验环境。

位置：

`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab`

## 已安装内容

| 模块 | 位置 | 说明 |
|---|---|---|
| Android platform-tools / ADB | `tools\platform-tools\platform-tools\adb.exe` | 便携安装，不改系统 PATH |
| scrcpy 4.0 | `tools\scrcpy\scrcpy-win64-v4.0\scrcpy.exe` | 便携安装，不改系统 PATH |
| Android SDK | `tools\android-sdk` | command line tools + platform android-36 + build-tools 36.0.0 |
| Python venv | `env\py311` | 项目独立虚拟环境 |
| third_party | `third_party` | GitHub参考仓库，按技术方向分类 |
| downloads | `downloads` | 保留原始下载包，方便复查 |
| captures | `captures` | 后续手机屏幕样本、录制文件 |
| logs | `logs` | 后续实验日志 |

## 已安装 Python 包

- `numpy`
- `opencv-python`
- `pillow`
- `imagehash`
- `fastapi`
- `uvicorn[standard]`
- `websockets`
- `pydantic`
- `psutil`
- `duckdb`
- `httpx`
- `mss`
- `onnxruntime`
- `rapidocr-onnxruntime`
- `vosk`
- `faster-whisper`
- `soundfile`
- `aiortc`
- `av`

没有安装 `torch`、`transformers` 等重模型依赖。第一阶段先验证屏幕流、抽帧、OCR、轻量ASR和停留分段，不急着上大模型。

## 已下载参考仓库

清单见：

```powershell
docs\environment_inventory_20260707.md
```

核心包括：ScreenStream、LiveKit Android SDK、OpenTok screenshare sample、screenpipe、Omi、Windrecorder、NVIDIA Live VLM WebUI、Vinci、VisionClaw、OpenVision、edX learning-assistant、DeepTutor。

已构建可安装 APK：

```powershell
downloads\apk\ScreenStream-4.4.1-FDroid-debug-built.apk
```

## 常用命令

在 PowerShell 中进入目录：

```powershell
cd C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab
```

检查环境：

```powershell
.\scripts\check_environment.ps1
```

查看手机是否被 ADB 识别：

```powershell
.\scripts\list_devices.ps1
```

有线授权后尝试 Wi-Fi ADB：

```powershell
.\scripts\adb_wifi_connect.ps1 -PhoneIp 192.168.x.x
```

安装本地构建的 ScreenStream APK：

```powershell
.\scripts\install_screenstream_apk.ps1 -Reinstall
```

启动 USB 镜像，不录制：

```powershell
.\scripts\start_scrcpy_usb.ps1
```

启动 USB 镜像，并录制到 `captures`：

```powershell
.\scripts\start_scrcpy_usb.ps1 -Record
```

## 华为手机准备要点

1. 打开开发者选项。
2. 打开 USB 调试。
3. 用数据线连接电脑。
4. 手机弹出 RSA 调试授权时，选择允许。
5. 运行 `.\scripts\list_devices.ps1`，看到 `device` 状态才算 ADB 通。

如果一直显示 `unauthorized`，需要在手机上重新确认授权；如果没有设备，可能需要换线、换USB口，或补华为手机驱动/华为手机助手。

## 当前边界

- 这里只做授权实验，不做无感录屏。
- 不抓短视频平台私有接口，不抓包破解，不绕过 DRM。
- 第一阶段目标是证明：真实手机当前屏幕能到 PC、能抽帧、能计算停留时长。
- 不在原 `华为杯` 文件夹里放实验工程，避免污染方案文件。

## 下一步硬件接入

按这个清单执行：

```powershell
docs\hardware_handoff_checklist_20260707.md
```

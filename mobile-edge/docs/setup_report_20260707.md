# 安装与验证报告

日期：2026-07-07  
目录：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab`

## 已完成

| 项目 | 状态 | 验证结果 |
|---|---|---|
| 独立桌面项目目录 | 已创建 | 未放入原 `华为杯` 文件夹 |
| Android platform-tools / ADB | 已便携安装 | `adb version` 正常 |
| scrcpy | 已便携安装 | `scrcpy 4.0` 正常 |
| Python 虚拟环境 | 已创建 | `env\py311` |
| OpenCV / numpy | 已安装 | `cv2 5.0.0`，`numpy 2.4.6` |
| FastAPI / WebSocket 相关包 | 已安装 | `fastapi 0.139.0`，`websockets 16.0` |
| ffmpeg | 本机已有 | `ffmpeg 8.1.1` 可用 |
| ADB 设备列表 | 已验证 | 当前未接手机，列表为空，属于正常状态 |

## 未安装

| 项目 | 原因 |
|---|---|
| Huawei 驱动/华为手机助手 | 等接入华为手机后看 ADB 是否识别；若不识别再补 |
| ScreenStream | 这是 Phase 1 可编程读流工具，等 USB/scrcpy 验证通过后再装 |
| torch / transformers / 本地VLM | 这是 Phase 3 视频理解工具，当前不提前装重环境 |
| LiveKit / WebRTC SDK | 这是正式工程路线，等 Phase 0-2 通过后再推进 |

## 当前可运行脚本

| 脚本 | 用途 |
|---|---|
| `scripts\check_environment.ps1` | 检查 ADB、scrcpy、ffmpeg、Python 依赖 |
| `scripts\list_devices.ps1` | 查看 ADB 是否识别手机 |
| `scripts\start_scrcpy_usb.ps1` | 启动 USB 手机镜像 |
| `scripts\start_scrcpy_usb.ps1 -Record` | 启动 USB 手机镜像并录制到 `captures` |

## 接华为手机时的第一步

1. 手机打开开发者选项。
2. 打开 USB 调试。
3. 用数据线连接电脑。
4. 手机弹出 RSA 调试授权时点允许。
5. 在项目目录运行：

```powershell
.\scripts\list_devices.ps1
```

看到 `device` 状态后，再运行：

```powershell
.\scripts\start_scrcpy_usb.ps1
```

如果显示 `unauthorized`，说明手机端没有完成授权。  
如果完全没有设备，优先换线/换USB口；仍不行再补华为驱动或华为手机助手。

## 边界记录

当前只完成环境准备，没有启动手机采集，没有安装重模型，也没有改动方案文件。下一步必须先用真实手机完成 ADB 识别和 scrcpy 画面验证，再决定是否进入 ScreenStream/RTSP 读流实验。

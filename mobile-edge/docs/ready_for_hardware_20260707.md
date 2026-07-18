# 硬件接入前状态总表

日期：2026-07-07

## 结论

当前实验环境已经可以接硬件。

已具备：

1. ADB / scrcpy USB 手机屏幕流验证。
2. Wi-Fi ADB 切换脚本。
3. Android SDK 37 + NDK 29 + JDK17 构建环境。
4. ScreenStream 4.4.1 本地构建 APK。
5. Python 实时服务、OCR、ASR、WebRTC、事件存储基础依赖。
6. Docker、Rust、GPU、ffmpeg 等本机基础能力。
7. 手机屏幕流、屏幕记忆、实时 VLM、眼镜 AI、学习助手方向的参考仓库。

## 首次接华为手机命令

```powershell
cd C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab
.\scripts\check_environment.ps1
.\scripts\list_devices.ps1
```

如果手机显示 `unauthorized`，在手机上确认 RSA 调试授权后再运行：

```powershell
.\scripts\list_devices.ps1
```

## 第一个实验：scrcpy 屏幕镜像

```powershell
.\scripts\start_scrcpy_usb.ps1
```

需要录制时：

```powershell
.\scripts\start_scrcpy_usb.ps1 -Record
```

## 第二个实验：安装 ScreenStream

```powershell
.\scripts\install_screenstream_apk.ps1 -Reinstall
```

APK 路径：

```powershell
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\downloads\apk\ScreenStream-4.4.1-FDroid-debug-built.apk
```

校验结果：

- APK ZIP 结构正常。
- `AndroidManifest.xml` 存在。
- APK Signature Scheme v2 验证通过。

## 第三个实验：Wi-Fi ADB

前提：USB 已授权，手机和电脑同一局域网。

```powershell
.\scripts\adb_wifi_connect.ps1 -PhoneIp 192.168.x.x
```

## 仍然没有做的事

- 没有下载大型 VLM 模型权重。
- 没有下载 Whisper/Vosk 具体语音模型。
- 没有改原始 `华为杯` 方案目录。
- 没有抓包、破解、绕过 DRM 或绕过系统授权。

## 下一步硬件实验要回答的问题

1. 华为手机 ADB 授权是否稳定。
2. scrcpy USB 延迟是否满足短视频刷动观察。
3. ScreenStream 在华为手机上能否输出屏幕流和音频。
4. 系统音频是否被短视频 App 允许捕获。
5. 评论区、消息页、搜索页、直播页、私密页面是否能被正确识别为非视频/敏感场景。
6. 第二视角模拟眼镜能否记录“学生是否真的在看手机/是否转向纸笔教材/是否自动播放”。

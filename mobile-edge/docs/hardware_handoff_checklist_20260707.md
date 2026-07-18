# 硬件到位后的接入检查表

日期：2026-07-07

## 1. 手机接入

目标：先证明“真实手机当前屏幕可以被授权采集、镜像、记录、抽帧”，不做隐私绕过。

步骤：

1. 华为手机打开开发者选项。
2. 打开 USB 调试。
3. 用数据线连接电脑。
4. 手机弹出 RSA 授权时选择允许。
5. 在项目目录运行：

```powershell
cd C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab
.\scripts\check_environment.ps1
.\scripts\list_devices.ps1
```

通过标准：

- `adb devices` 中出现 `device`。
- 不能是 `unauthorized`。
- 如果没有设备，先换线/换 USB 口，再考虑手机驱动。

## 2. USB 屏幕流验证

```powershell
.\scripts\start_scrcpy_usb.ps1
```

如果需要录制样本：

```powershell
.\scripts\start_scrcpy_usb.ps1 -Record
```

安装本地构建的 ScreenStream APK：

```powershell
.\scripts\install_screenstream_apk.ps1 -Reinstall
```

安装后在手机上打开 ScreenStream，按系统提示授权屏幕采集。这个授权是实验前台授权，不是无感录屏。

通过标准：

- PC 能看到手机当前画面。
- 手机正常刷动时没有明显卡顿。
- 录制文件出现在 `captures`。

## 3. Wi-Fi ADB 验证

前提：USB 已经授权成功，并且手机和电脑在同一局域网。

```powershell
.\scripts\adb_wifi_connect.ps1 -PhoneIp 192.168.x.x
```

通过标准：

- `adb devices` 中出现 `192.168.x.x:5555 device`。
- 拔掉数据线后仍能 `adb devices` 看到设备。

注意：Wi-Fi ADB 是开发验证路线，不是最终普通学生使用方式。

## 4. 第一视角模拟

没有真实眼镜前，先用第二台手机或运动相机模拟眼镜第一视角。

需要验证：

- 能否稳定拍到学生是否看手机。
- 能否识别手机被放一边自动播放。
- 能否识别视线/头部从手机转移到纸笔、教材、电脑。
- 能否和手机屏幕流在时间线上对齐。

第一视角流暂时不承担“看清短视频内容”的主责任。内容语义主证据仍来自手机屏幕流。

## 5. 不能做的事

- 不抓短视频平台私有接口。
- 不抓包破解。
- 不绕过 DRM / `FLAG_SECURE`。
- 不偷读聊天、支付、登录、相册等隐私页面。
- 不把短停留内容强行生成学习任务。

## 6. 第一次硬件实验要记录的数据

每次实验至少记录：

- 手机型号、系统版本。
- 连接方式：USB / Wi-Fi ADB。
- App 场景：短视频 feed、评论区、消息页、搜索页、非视频页。
- 是否能捕获画面。
- 是否能捕获音频。
- 画面延迟主观感受。
- 录制文件路径。
- 出现的降级原因：`capture_blocked`、`audio_blocked`、`private_surface`、`frame_low_quality` 等。

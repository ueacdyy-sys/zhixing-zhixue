# 知行智学 Android RTSP 内核

本目录是对 ScreenStream MIT 代码的受控改造，只保留用户主动授权后的本地 RTSP 媒体运输能力。

## 当前范围

- Android 学生端：本地会话、候选、通知回执与设备状态。
- 媒体内核：RTSP、MediaProjection、视频编码和受控设备音频。
- 领域层：`learning-domain` 与 `learning-application`，不依赖 Android 或 RTSP 实现细节。

不包含 MJPEG、WebRTC、广告、Firebase、崩溃分析、上游商店分发或上游云信令。

## 构建

Windows 从 ASCII Junction 构建：

```powershell
cd C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source
.\gradlew.bat --offline :learning-domain:test :app:assembleDebug :app:lintDebug
```

第三方版权和 MIT 许可见 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。

# 知行智学移动边缘端

当前 Android 主工程位于 `third_party/screenstream_source`，只保留用户授权后的 RTSP 媒体传输、学生端候选/回执和本地设备会话能力。

## 构建入口

真实项目目录保持为 `C:\Users\Administrator\Desktop\知行智学`。Windows 上必须从 ASCII Junction 构建，以避免 Gradle/Kotlin Worker 错误解码中文路径：

```powershell
cd C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source
.\gradlew.bat --offline :learning-domain:test :app:assembleDebug :app:lintDebug
```

`local.properties` 是未跟踪的本机 SDK 配置；当前 SDK 位于 `mobile-edge\tools\android-sdk`。

## 运行边界

- RTSP 是唯一手机媒体传输内核；不保留 MJPEG、WebRTC、广告、Firebase 或上游商店变体。
- 只能由学生主动完成 MediaProjection 授权后开始媒体传输；不控制第三方平台页面，不自动滑动或播放。
- 单帧/OCR、无同源音频或时间不连续媒体只能输出 `CANDIDATE_ONLY`。
- 真机、PC 入站、ASR、VLM 的完整正向链验收见根仓库的 Spec Kit；构建成功不替代真机验证。

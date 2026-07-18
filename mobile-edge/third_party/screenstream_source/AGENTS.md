# 知行智学 Android 工程约束

## 产品与模块

- `app`：学生端 Compose 壳与授权编排。
- `common`：通用设置、通知、日志和 UI 工具。
- `rtsp`：唯一媒体传输内核；只处理用户授权后的 RTSP。
- `learning-domain`：纯 Kotlin 领域模型与质量门控；不得依赖 Android、RTSP、Koin 或平台规则。
- `learning-application`：领域用例与端口。
- `edge-android`：Android 本地存储、通知、会话和 RTSP 适配器。

不保留 MJPEG、WebRTC、PlayStore 风味、广告、Firebase 或上游云服务。

## 构建

真实目录为 `C:\Users\Administrator\Desktop\知行智学`。Windows 构建必须从 ASCII Junction 启动：

```powershell
cd C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source
.\gradlew.bat --offline :learning-domain:test :app:assembleDebug :app:lintDebug
```

`local.properties` 仅配置本机 SDK，不得加入 Git。Debug 使用 Android 标准 debug keystore；发布签名由受控发布流程提供，禁止在源码、脚本或文档中硬编码口令。

## 行为与安全

- 用户必须主动完成 MediaProjection 授权；不得自动录屏、自动控制第三方 App 或绕过 DRM。
- 单帧/OCR、无同源音频或时间不连续媒体只能为 `CANDIDATE_ONLY`。
- Debug 广播只可供 ADB shell 调试，不得进入发布控制面，不记录 Intent extras。
- 保留 MIT 许可证和 `THIRD_PARTY_NOTICES.md`；不得沿用上游隐私政策、商店素材或外部服务声明。

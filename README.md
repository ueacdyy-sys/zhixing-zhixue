# 知行智学

面向学习机会窗识别的多端智能学习助手与过程证据复盘系统。

## 应用边界

- `mobile-edge/third_party/screenstream_source/`：当前唯一 Android 学生端与 RTSP 媒体运输内核；包含 `learning-domain`、`learning-application`、`edge-android` 与 Compose 学生端。手机仅在用户主动授权后传输媒体，PC 端再进行受控分析。
- `apps/pc-workbench/`：PC 学习实践、证据工作台、教师复核界面。
- `services/local-hub/`：本地可信中枢；负责会话、授权、同步、证据、分析调度与审计。
- `specs/`：Spec Kit 的需求、架构、契约、计划和任务。

## 当前构建事实

- Android SDK/NDK 位于 `mobile-edge/tools/android-sdk/`。Windows 下 Android/Gradle 构建统一从 `C:\ZhixingZhixue` Junction 启动；该 ASCII 别名指向本项目根目录，用于避免 Kotlin/Gradle Worker 将中文路径错误解码。`local.properties` 已指向该别名下的 SDK。
- `apps/mobile-android/` 的自写 `MediaProjection + MediaRecorder` 原型已移除，不再作为采集或发布路径。
- 真实手机公开媒体的单帧/OCR、无同源音频或时间不连续证据只能保留为 `CANDIDATE_ONLY`，不得生成兴趣、知识、诊断或强制任务结论。

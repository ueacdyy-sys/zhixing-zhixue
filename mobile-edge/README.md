# 知行智学移动边缘端

## 当前实现

Android 主工程位于 `third_party/screenstream_source`，实现RTSP媒体传输内核。

### 核心特性
- 仅在用户主动授权MediaProjection后传输媒体
- RTSP作为唯一媒体传输协议
- 学生端候选/回执和本地设备会话管理

### 移除的上游功能
不保留以下ScreenStream上游特性:
- MJPEG传输协议
- WebRTC传输协议
- 广告SDK
- Firebase服务
- 商店变体

## 构建入口

### Windows特殊要求
**必须从ASCII路径构建**,避免Gradle/Kotlin Worker中文路径解码错误。

推荐方式 - 创建Junction:
```powershell
# 以管理员权限运行
New-Item -ItemType Junction -Path "C:\ZhixingZhixue" -Target "C:\Users\86152\Desktop\zhixing-zhixue"
```

### 构建命令
```powershell
cd C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source
.\gradlew.bat --offline :learning-domain:test :app:assembleDebug :app:lintDebug
```

### SDK配置
- Android SDK位于: `mobile-edge\tools\android-sdk\`
- `local.properties` 是未跟踪的本机SDK配置
- 必须配置SDK路径指向Junction下的SDK

示例 `local.properties`:
```properties
sdk.dir=C:\\ZhixingZhixue\\mobile-edge\\tools\\android-sdk
```

## 运行边界

### 隐私与授权
- **用户授权**: 只能由学生主动完成MediaProjection授权后开始媒体传输
- **不控制第三方**: 不控制第三方平台页面,不自动滑动或播放
- **本地优先**: 所有处理在本地中枢完成,手机仅传输媒体流

### 证据分级约束
以下情况的媒体**只能输出** `CANDIDATE_ONLY`:
- 单帧图像(非连续视频)
- OCR文本(无同源音频)
- 时间不连续的媒体片段

不得为上述情况生成:
- 兴趣结论
- 知识诊断  
- 学习任务推荐
- 强制干预措施

### 实时入口
当前保留:
- 连续媒体入站通道
- 三路分析管道
- 封存窗口融合

已剥离:
- v2 L0迁移桥(作为待接线组件保留)
- 旧`candidate_card.v1`通知/outbox(仅作只读迁移兼容)

## 验收要求

真机、PC入站、ASR、VLM的完整正向链验收见:
- 根仓库的Spec Kit: `specs/004-realtime-learning-core/`
- TDD测试矩阵: `docs/tdd/test-matrix.md`

**注意**: Gradle构建成功不能替代真机验证。

## 环境要求

- JDK 17+
- Gradle 9.5+ (通过wrapper自动下载)
- Android SDK:
  - Command-line Tools 19+
  - Platform-Tools 37+
  - Android 35 (API Level 35)
  - Build-Tools 35+

## 相关文档

- [环境配置](../docs/环境配置与验收总览.md)
- [贡献约束](../CONTRIBUTING.md)
- [安全说明](../SECURITY.md)

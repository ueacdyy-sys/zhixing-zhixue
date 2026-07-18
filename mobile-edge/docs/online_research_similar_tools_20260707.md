# 双流兴趣证据系统相似项目与工具联网调研

日期：2026-07-07  
调研目标：验证“手机屏幕流 + 眼镜第一视角流 + 电脑边缘理解 + 手机微任务反馈”是否已有相似工具、项目或技术路线，并判断哪些可以复用，哪些只能参考。  

## 1. 总结论

没有找到一个现成项目完整覆盖本方案。

但已经存在五类相近能力：

1. **手机屏幕流采集/传输**：ScreenStream、LiveKit、OpenTok sample、AndroidStreamControl、scrcpy。
2. **桌面/屏幕AI记忆**：screenpipe、Omi、Windrecorder、Dayflow、Memento Native。
3. **实时VLM视频理解**：NVIDIA Live VLM WebUI、Vinci、各类 streaming video LLM 项目。
4. **第一人称/眼镜AI助手**：Vinci、EgoLife、OpenVision、MentraOS、Meta Wearables Device Access Toolkit。
5. **AI学习助手/微学习工具**：edX learning-assistant、DeepTutor、各种视频转录总结学习工具。

这些项目说明：**你现在的方案不是凭空想象，技术趋势是存在的；但你的方案差异在于“学习过程证据链”和“双流融合后生成兴趣探索/桥接任务”，不是单纯屏幕录制、单纯眼镜助手、单纯视频总结或单纯AI tutor。**

本轮补充调研后，结论更明确：

- **不能把手机浏览器 `getDisplayMedia` 当主路线**：OpenVidu 文档、Zoom 开发者论坛和 MDN 兼容性说明都指向移动浏览器屏幕共享支持不足，真实手机端必须走原生 App 的 MediaProjection / ReplayKit 路线。
- **眼镜方向已经出现更接近的工程样例**：VisionClaw、OpenVision、MentraOS、Meta Wearables Device Access Toolkit 都在做“眼镜摄像头/麦克风 -> 手机 App -> 实时 AI”的链路，说明“眼镜先连手机、手机做会话中枢”比“眼镜必须直连电脑”更符合现实使用频率。
- **屏幕记忆工具的工程策略有价值但不能照搬**：Dayflow、Windrecorder、screenpipe 多采用低频采样、分段、批处理、本地索引，适合复盘和时间线；本项目的短视频场景要求更细粒度的停留事件、滑动/回看/评论/消息状态识别，以及候选片段触发式 VLM。
- **NotebookLM 类工具不是对标产品**：它支持 YouTube URL、音频、文档等“已给定来源”的理解，核心是 source-grounded research；本项目要求的是正在发生的手机浏览内容流和过程状态流的实时理解。

## 2. 和本方案最接近的技术组合

最接近本项目的组合不是一个产品，而是下面几类工具拼起来：

```text
Android MediaProjection / ScreenStream / LiveKit
  -> 手机屏幕流

Meta Wearables Toolkit / MentraOS / OpenVision / Vinci / EgoLife
  -> 眼镜第一视角和过程理解

Live VLM WebUI / Vinci / streaming video LLM
  -> 实时或准实时视频理解

screenpipe / Omi / Windrecorder
  -> 本地时间线、屏幕记忆、证据索引

本项目自研层
  -> 兴趣原子、双流融合、机会窗、证据卡、微任务门控
```

也就是说，可复用的是底座，不可复用的是教育语义层和证据闭环。

## 3. GitHub 与开源工具矩阵

### 3.1 手机屏幕流采集

| 项目 | 类型 | 能力 | 对本项目价值 | 限制 |
|---|---|---|---|---|
| ScreenStream | Android开源App | 通过 MediaProjection 将屏幕和音频以 MJPEG、WebRTC、RTSP 输出 | Phase 1 可用，不用先写采集App | 官方说明延迟至少0.5-1秒，且不为高清视频播放优化 |
| scrcpy | Android镜像工具 | USB/TCP低延迟镜像和录制 | Phase 0 验证真实手机当前屏幕 | 依赖ADB，不适合最终普通用户 |
| OpenTok Android screenshare sample | WebRTC示例 | MediaProjection + WebRTC 自定义视频设备 | 正式手机App可参考 | 示例级，不含本项目事件层 |
| AndroidStreamControl | WebRTC远程控制 | Android屏幕远程流和控制 | 可参考信令/WebRTC结构 | Star少，成熟度需验证 |
| LiveKit screen sharing | SDK/文档 | Android MediaProjection、iOS ReplayKit、跨平台 screen track | 正式互联路线 | 需要正确处理权限、前台服务、信令 |

重要依据：

- ScreenStream README 明确支持 Local MJPEG、Global WebRTC、RTSP；使用 Android MediaProjection，支持屏幕和音频流。
- Android 官方 MediaProjection 要求 Android 14+ 声明 `mediaProjection` 前台服务类型，并且每次会话需要用户同意。
- LiveKit 文档说明屏幕共享在 Android 上通过 `MediaProjectionManager`，iOS 上通过 ReplayKit Broadcast Extension。
- Fora Soft 开发者博客强调 Android 14+ 必须先启动 `mediaProjection` 前台服务再请求投影；推荐 720p/15fps/1.5-2Mbps 作为现实基线。

### 3.2 屏幕/音频 AI 记忆系统

| 项目 | 类型 | 能力 | 对本项目价值 | 限制 |
|---|---|---|---|---|
| screenpipe | 开源/源可见屏幕记忆 | 持续捕获屏幕和音频，本地存储，可AI搜索 | 本地证据时间线、隐私、本地优先架构可参考 | 主要是桌面，不是手机短视频 |
| Omi | 开源AI记忆/可穿戴生态 | 捕获屏幕和对话、实时转写、总结行动项，覆盖桌面/手机/可穿戴 | “屏幕 + 对话 + wearable”方向很接近 | 目标是个人第二大脑，不是学习证据卡 |
| Windrecorder | 开源屏幕记忆 | 本地记录屏幕、小体积存储、OCR/图像描述、活动统计 | 本地时间线、OCR、隐私设计可参考 | 桌面为主，不是实时双流 |
| Dayflow | 开源工作日志 | 把屏幕转为工作时间线 | 时间线叙事和活动归纳可参考 | 工作场景，不是教育/手机 |
| Memento Native | 本地屏幕记忆 | OCR、语义召回、App-aware timeline | app-aware timeline 可参考 | macOS端，不是移动端 |

判断：这类项目证明“持续屏幕捕获 + 本地AI记忆 + 时间线”已有生态，但它们通常缺少：

- 手机短视频场景；
- 第一视角过程流；
- 学习机会窗；
- 兴趣探索卡；
- 教师/学生复盘证据卡。

### 3.3 第一人称/眼镜 AI 助手

| 项目 | 类型 | 能力 | 对本项目价值 | 限制 |
|---|---|---|---|---|
| Vinci | GitHub项目/论文 | 实时 egocentric VLM assistant，支持智能手机和可穿戴摄像头，处理长视频流并回答当前/历史观察问题 | 最接近“第一人称实时理解”的研究原型 | 环境重，README显示 checkpoints 可能超过100GB；不是教育场景 |
| EgoLife | 数据集/系统 | AI眼镜连续记录日常生活，EgoGPT + EgoRAG 支持长上下文问答 | 证明“眼镜日常过程记录 + RAG + QA”方向成立 | 研究数据/模型，不是可直接部署工具 |
| OpenVision | iOS开源App | 连接 Meta Ray-Ban 智能眼镜到AI助手，支持云端或端侧模型 | 很适合观察“手机App作为眼镜AI中枢”的路线 | iOS + Meta Ray-Ban，硬件/系统依赖强 |
| MentraOS | 开源智能眼镜OS/SDK | 直播第一视角、字幕、AI对话、拍照，BLE连接手机App | 可参考眼镜OS和手机连接路线 | 依赖兼容眼镜生态 |
| Meta Wearables Device Access Toolkit | 官方开发者工具 | 开放AI眼镜摄像头/音频给移动App扩展 | 说明“手机App接入眼镜相机/音频”是官方趋势 | 仍是 developer preview，发布和权限受限 |
| VisionClaw | GitHub项目 | Meta Ray-Ban 眼镜摄像头/麦克风通过手机App连 Gemini Live/OpenClaw；约1fps视觉帧 + 实时音频 | 最接近“眼镜第一视角 -> 手机 -> 实时AI/动作”的工程样例 | 目标是通用助手，不做学习过程证据和手机屏幕流融合 |

判断：第一人称路线确实有人在做，而且明显走向“手机App + 眼镜 + AI助手”。这支持我们的“眼镜优先连手机，手机作为会话中枢”的架构，而不是让眼镜必须直连电脑。

对本项目的含义：眼镜流不要先追求高帧率“看清手机内容”，而应优先承担过程证据角色：是否真的在看、是否离开手机、是否自动播放、是否切到纸笔/教材/电脑、是否从兴趣内容迁移到真实学习行为。手机屏幕流仍然是内容语义主证据。

### 3.4 实时 VLM / 视频流理解

| 项目 | 类型 | 能力 | 对本项目价值 | 限制 |
|---|---|---|---|---|
| NVIDIA Live VLM WebUI | GitHub项目 | WebRTC摄像头流到VLM，做实时AI分析和性能测试 | PC端 Phase 3 可作为VLM实验基座 | 偏摄像头/桌面测试，不含手机屏幕和教育语义 |
| Vinci | 研究原型 | 在线 egocentric video-language assistant | 第一视角流理解思路可参考 | 模型重 |
| Building Egocentric Procedural AI Assistant | GitHub综述 | 汇总实时/流式视频理解、主动交互、过程任务助手 | 研究地图，可继续跟踪 | 不是代码主线 |
| GPT-4o media stream capture demos | Web demo | 抽帧后调用AI分析多媒体流 | 可参考“定时抽帧 + AI分析” | 多为demo，实时性和隐私不足 |
| AWS camera + Bedrock sample | 云端样例 | 实时摄像头到云端生成式AI分析 | 工业实时视频分析架构可参考 | 云端，不适合未成年人/本地优先 |

关键判断：实时理解领域已经形成共识：**不是每帧都跑大模型，而是抽帧、采样、缓存、流式记忆、触发式推理。** 这和我们前面定义的“采集不等推理、短停留不进VLM、VLM只处理候选片段”一致。

### 3.5 AI学习助手/微学习

| 项目 | 类型 | 能力 | 与本项目关系 |
|---|---|---|---|
| edX learning-assistant | 平台学习助手 | 面向课程平台的AI学习助手后端/前端 | 学习助手，但默认在正式学习平台内 |
| DeepTutor | AI tutor | RAG、题目、学习路径、知识库 | 学习任务强，但不是从真实兴趣流启动 |
| AWS sample-ai-learning-assistant | 媒体上传转录/总结 | 上传音视频后转录、总结、提取洞察 | 更像 NotebookLM，不是实时 |
| YouTube/PDF learning assistant 项目 | 视频/PDF总结 | 把已有材料变成结构化知识 | 有学习内容生成，但没有过程证据 |

判断：学习助手很多，但大多从“学生已进入学习材料/课程/题目”开始。你的方案从“手机兴趣入口 + 过程证据 + 状态/第一视角 + 复盘”开始，这一点仍然是差异点。

## 4. 开发者博客和论坛调研

### 4.1 Android屏幕共享开发者共识

Fora Soft 的 Android WebRTC screen sharing 指南给出几个现实工程结论：

- Android 14+ 下，`mediaProjection` 前台服务顺序是关键。
- 720p / 15fps / 1.5-2Mbps 是移动屏幕共享较现实的基线。
- 黑屏通常来自 `FLAG_SECURE` 或 DRM，不能绕过。
- 系统音频可用 `AudioPlaybackCaptureConfiguration`，但源App可拒绝捕获。
- 需要用真实设备矩阵测试，不是单元测试能解决。

这直接约束本项目：不能承诺所有短视频/音频都可抓；必须记录 `capture_blocked`、`audio_blocked`、`frame_low_quality` 等降级原因。

### 4.2 社区问题说明这不是简单功能

- Stack Overflow 早期讨论显示 Android screen sharing over WebRTC 可行，但历史方案已经过时，只能证明方向不是空想。
- OpenVidu 社区指出 Android Chrome 不支持 `getDisplayMedia`，这说明不能把浏览器网页方案当手机App主路线。
- flutter-webrtc issue 中出现 `FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION` 相关崩溃，说明 Android 14+ 的前台服务要求是实际坑点。
- Google AI Developers Forum 有开发者询问“如何让AI看到/听到桌面并低延迟互动”，说明实时多模态助手是开发者社区正在探索的问题。

### 4.3 移动端系统级屏幕 AI/浮层工具的参考边界

还发现一些 Android 屏幕 AI/辅助工具方向，例如 Orion AI screen reader、AI Screen Translator、Arc AI Screen Assistant，以及开发者关于 AccessibilityService/overlay 的讨论。它们说明“系统级屏幕上下文 + 浮层反馈”是存在需求的，但这条路线在本项目里只能谨慎使用：

- AccessibilityService 可以帮助识别前台 App、窗口/控件结构、用户操作事件，但它是高敏权限，不应被设计成偷读私信、密码、支付页面或隐私内容的通道。
- OCR/浮层工具可参考反馈形态，但不能替代 MediaProjection 屏幕流，因为短视频内容的画面、字幕、人物、镜头变化、滑动停留都不是纯 OCR 能解决。
- 真正可用的系统必须先有“非视频/隐私场景防呆”：消息、聊天、支付、登录、相册、系统通知、私密页面默认不进入内容理解，只记录降级原因或会话状态。

## 5. 本项目和现有项目的差异

| 能力 | 现有工具是否有 | 本项目要求 |
|---|---|---|
| 手机屏幕流采集 | 有，ScreenStream/LiveKit/scrcpy | 要变成兴趣流事件和停留分段 |
| 眼镜第一视角 | 有，Vinci/EgoLife/OpenVision/Mentra | 要做过程证据，不做注意力结论 |
| 实时视频理解 | 有，Live VLM/Vinci/streaming VLM | 要增量兴趣原子，不是视频摘要 |
| 本地时间线 | 有，screenpipe/Windrecorder/Omi | 要统一三流证据链 |
| 学习助手 | 有，edX/DeepTutor等 | 要从非正式兴趣流迁移，不默认进入学习任务 |
| 双流融合 | 部分有，多摄像/egocentric研究 | 要融合手机屏幕流 + 第一视角过程流 |
| 微任务生成 | 有微学习/AI tutor | 要经过内容门、行为门、过程门、打扰门 |
| 证据卡/降级 | 少见 | 是本方案核心 |

最重要的差异：**已有项目多是“记录/总结/问答/助手”，本项目是“学习过程证据系统”。**

## 6. 可复用路线建议

### 6.1 第一阶段直接复用/借鉴

| 目标 | 推荐复用 |
|---|---|
| 快速验证手机屏幕流 | scrcpy、ScreenStream |
| 正式Android屏幕采集 | Android MediaProjection + LiveKit/getstream/webrtc-android |
| 电脑端实时VLM实验 | NVIDIA Live VLM WebUI |
| 本地时间线/证据存储 | screenpipe/Windrecorder 的本地优先思路 |
| 眼镜模拟 | 手机B/运动相机；后续参考 OpenVision/Mentra |

### 6.2 不建议直接采用

| 工具/方向 | 原因 |
|---|---|
| 完全套用 screenpipe | 桌面屏幕记忆，不解决手机短视频和双流 |
| 完全套用 Vinci | 模型/环境重，且不是教育证据链 |
| 完全套用 AI tutor | 从学习材料开始，不从兴趣流和过程证据开始 |
| 完全依赖云端VLM | 隐私、未成年人、网络、成本风险 |
| 只用眼镜拍手机屏幕 | 内容识别不如手机直抓，不能替代屏幕流 |

## 7. 对开发路线的更新

基于调研，路线不变，但优先级更清晰：

```text
Phase 0：scrcpy/ScreenStream验证真实手机屏幕流
Phase 1：手机App原型，MediaProjection + dwell + surface classifier + local queue
Phase 2：第一视角模拟，手机B/运动相机模拟眼镜过程流
Phase 3：电脑端边缘服务，参考 Live VLM WebUI + 本地时间线架构
Phase 4：手机-电脑互联，优先WebSocket；需要低延迟视频轨再上LiveKit/WebRTC
Phase 5：真实眼镜接入，关注 Meta Toolkit / MentraOS / OpenVision / VisionClaw / 厂商SDK
Phase 6：教育语义自研：兴趣原子、机会窗、证据卡、微任务门控
```

这里的关键是：**先不要造完整智能眼镜系统，也不要先造大模型学习助手；先把手机屏幕流和第一视角流变成可复查事件。**

## 8. 现成工具和本项目模块映射

| 本项目模块 | 可参考项目 | 自研程度 |
|---|---|---|
| 手机屏幕流采集 | ScreenStream、LiveKit、OpenTok sample | 中 |
| 手机端本地队列 | screenpipe/Windrecorder本地优先理念 | 中 |
| 电脑端VLM实验 | Live VLM WebUI、Vinci | 中 |
| 眼镜连接 | Meta Toolkit、MentraOS、OpenVision、VisionClaw | 高，取决于硬件 |
| 双流时间对齐 | Egocentric research / multi-stream video systems | 高 |
| 兴趣原子 | 无直接可用 | 高 |
| 微任务门控 | AI tutor + microlearning理念 | 高 |
| 证据卡/降级机制 | 本方案自有 | 高 |

## 9. Go/No-Go 结论

| 问题 | 结论 |
|---|---|
| 是否有人做类似方向 | 有，分散在屏幕记忆、实时VLM、眼镜AI助手、AI tutor 中 |
| 是否有完全一样的开源项目 | 暂未发现 |
| 是否能复用现成工具减少开发 | 能，尤其是屏幕流、WebRTC、VLM测试、本地时间线 |
| 是否需要自研核心 | 必须，自研双流融合、兴趣原子、证据卡、微任务门控 |
| 当前方案是否和市场/研究趋势一致 | 一致，而且更聚焦教育过程证据 |
| 是否可以继续推进实验 | Go，但先做最小双流验证，不直接做完整产品 |

## 10. 重点来源

- ScreenStream GitHub：<https://github.com/dkrivoruchko/screenstream>
- Android MediaProjection：<https://developer.android.com/media/grow/media-projection>
- LiveKit screen sharing：<https://docs.livekit.io/transport/media/screenshare/>
- OpenTok Android screen share sample：<https://github.com/nexmo-se/opentok-screenshare-android-sample>
- Fora Soft Android WebRTC screen sharing guide：<https://www.forasoft.com/blog/article/android-webrtc-screen-sharing>
- NVIDIA Live VLM WebUI：<https://github.com/nvidia-ai-iot/live-vlm-webui>
- Vinci：<https://github.com/OpenGVLab/vinci>
- EgoLife：<https://egolife-ai.github.io/blog/>
- Ego4D：<https://ego4d-data.org/>
- Awesome Egocentric Vision：<https://github.com/Sid2697/awesome-egocentric-vision>
- Building Egocentric Procedural AI Assistant：<https://github.com/z1oong/Building-Egocentric-Procedural-AI-Assistant>
- screenpipe：<https://github.com/screenpipe/screenpipe>
- Omi：<https://github.com/BasedHardware/omi>
- Windrecorder：<https://github.com/yuka-friends/Windrecorder>
- Meta Wearables Device Access Toolkit：<https://developers.meta.com/blog/introducing-meta-wearables-device-access-toolkit/>
- MentraOS repositories：<https://github.com/orgs/Mentra-Community/repositories>
- OpenVision：<https://github.com/rayl15/OpenVision>
- VisionClaw GitHub：<https://github.com/Intent-Lab/VisionClaw>
- VisionClaw paper：<https://arxiv.org/abs/2604.03486>
- Android CompanionDeviceManager：<https://developer.android.com/reference/android/companion/CompanionDeviceManager>
- Google Nearby Connections：<https://developers.google.com/nearby/connections/overview>
- OpenVidu screen share docs：<https://docs.openvidu.io/en/stable/advanced-features/screen-share/>
- Zoom developer forum mobile getDisplayMedia：<https://devforum.zoom.us/t/are-there-any-plans-to-enable-share-screen-using-mobile-devices/108272>
- LiveKit Android 14 screen share issue：<https://github.com/livekit/client-sdk-flutter/issues/555>
- MDN getDisplayMedia：<https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia>
- NotebookLM source overview：<https://support.google.com/notebooklm/answer/14276468>
- edX learning-assistant：<https://github.com/edx/learning-assistant>
- DeepTutor：<https://github.com/HKUDS/DeepTutor>

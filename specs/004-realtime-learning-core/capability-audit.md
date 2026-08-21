# 现有能力审计与处置清单

## 1. 总体裁决

**当前系统严重偏离新冻结需求。** 偏离集中在业务状态机和跨端契约，而不是 V5 外观或媒体传输本身。应进行替换式重构：保留经验证的授权、媒体运输、TLS 配对、可靠投递和视觉资产；停止扩展 candidate/visit 业务链，以新模型并行落地并迁移。

## 2. Android

| 现有位置 | 实际能力 | 处置 | 理由 |
|---|---|---|---|
| `V5NativeApp.kt` | V5 Compose 视觉、L 页面壳、手写路由且直接调用服务 | 保留视觉；拆分重构 | 单文件约 2700 行，状态/依赖不可测，L2/L3/L4 含义不符 |
| `ScreenStreamRtspAdapter.kt`、连接页 | 用户授权 MediaProjection → RTSP | 保留为 `PhoneCaptureSource` | 是真实运输适配器，不应承载业务判断 |
| `V5ConnectionPage` / 当前 capture start API | 系统 MediaProjection 授权后只把 RTSP port/path 交给 PC；无 capture scope、consent snapshot 或未知来源失败关闭 | 必须替换入口 payload | 像素流不等于应用/视频 ID；不能将页面文案当成私密页面过滤技术门 |
| `PcDeliveryClient.kt`、`PcSyncForegroundService.kt` | PC TLS 配对、SPKI pin、轮询、落库后 ACK、恢复代次 | 保留并改接 v2 | 是可靠投递基础；只负责 transport |
| `AndroidPcDeliveryLinkStore`、`PcDeliveryClient.kt` | 配对 bearer token、cursor 保存在普通 SharedPreferences；当前入站只识别旧 `mobile_result_message.v1` | 不复用认证/入站 schema | bearer 不可明文落盘；v2 必须使用 Keystore 设备凭据 + 短期访问 token，且只接收新 package/事实/receipt 契约 |
| `PcSyncForegroundService.kt` | `START_STICKY` 使已配对设备可在系统重启服务后继续同步；停止意图未形成独立持久用户停用状态 | 增加 v2 用户停止门 | 用户主动停止/撤回后不得因服务恢复而重新建立 capture、轮询或通知投递 |
| `AndroidStudentNotice.kt` | Android 高优先级 MessagingStyle 通知 | 保留并改 payload | `candidateId` 必须替换为稳定 `briefId`；`packageId + packageRevisionId` 只定位内容版本 |
| `AndroidKnowledgeGraphRepository.kt` | 本地图谱与手工编辑 | 迁移/复用 | 保留人工修订；AI 自动图谱必须来自新内容包 |
| `ContentConceptCanvas` 与 `KnowledgeGraphProjector` | V5 硬编码内容节点；PC 自动关联同时写长期画像 | 停止作为生产内容图谱 | 正式 L2 必须按 `briefId` 加载其 `ContentGraphRevision`；切断自动 `profile_entries` 写入 |
| `CandidateCard.kt`、`PcCandidateCardInbox.kt`、旧 codec | 三模态候选、当前 visit/新鲜度通知门 | 冻结后删除 | 不能表达 L0 增量、兴趣与内容包 |
| SharedPreferences JSON stores | 候选、学习内容、路径、回执 | 停止扩展并迁到 Room | 无事务、无迁移、无法承接实时实体 |
| `MobileDirectAgentProvider.kt` | OpenAI-compatible 聊天 API | 与媒体链隔离 | 不是无 PC 云端视频/图文分析，不得冒充 |
| 眼镜相关枚举/UI | 来源标签与提示页面 | 重建采集适配器 | 尚无 BLE/Wi-Fi/视频 ingestion，不能声称已接入 |

## 3. PC 服务端

| 现有位置 | 实际能力 | 处置 | 理由 |
|---|---|---|---|
| `local_agent_gateway.py` | FastAPI、配对、SQLite outbox、HTTPS/本地模型配置 | 保留 gateway 骨架，新增 v2 API | 可作为 PC LocalModel transport；现有内容 schema 过旧 |
| gateway `devices` token / revoke 与 capture supervisor | token 当前为一年期且每次使用续期；撤销只标记 device，未级联停止同设备 capture worker/outbox lease | 替换认证与撤销流程 | 必须有设备密钥证明、轮换、失效与撤销级联；不能只让后续请求 401 而让已运行 worker 继续 |
| `realtime_runtime/ledger.py` | 分片、PTS/哈希、任务 lease、车道证据、候选融合 | 保留媒体账本与完整性；重构领域输出 | 目前终点是 `FusedCandidate(CANDIDATE_ONLY)`，不是 episode/L0/内容包 |
| `realtime_runtime/semantic_state.py` | 仅开放 visit 的 TRIMODAL 候选投影 | 废弃替换 | `can_offer_l1` 与兴趣型 L1 正面冲突 |
| `candidate_notice_dispatcher.py` | 当前 visit + TRIMODAL + 十秒新鲜度经 ADB 发候选通知 | 删除运行链 | L1 不应依赖 current visit、候选或 ADB 广播 |
| `realtime_fragment_worker.py`、`pipeline.py` | 片段处理/封存与并行 lane 的技术基础 | 保留并改接 `RealtimeSemanticFact` | 必须从“候选融合”转向连续语义增量和 episode 聚合 |

## 4. 推荐 Android 工程形态

```text
core:model          纯 Kotlin 领域实体、reducer、契约
core:designsystem   NativeV5Tokens 与通用 Compose 组件
core:database        Room、DAO、迁移、事务
core:network         v2 schema、TLS/transport 基础
feature:capture      授权、PhoneCaptureSource、行为采集、连接状态
feature:discover     L0/L1 历史记录
feature:l1           通知落点、概念来源、解释、精析
feature:knowledge    L2 ContentGraphRevision 与 StudentGraphPatch
feature:practice     L3 客观题与 L4 论证
feature:profile      可撤销的证据索引与助手
data:pc / data:cloud AnalysisTransport 的两个实现
```

UI 固定为 **Jetpack Compose + Material 3 + 既有 V5 tokens/组件**。新增 Navigation Compose、Room、Kotlin serialization/HTTP schema 校验；继续使用现有 Koin，收敛 `MobileAppServices` service locator，禁止同时引入 Hilt。每个 feature 使用 `ViewModel + StateFlow + collectAsStateWithLifecycle`。WorkManager 仅处理延迟重试、历史同步和清理，实时热路径继续使用前台媒体服务与 Flow。

## 5. 现有可保留/不可删除边界

- 保留：MediaProjection/RTSP、PC pairing/TLS pin、可靠 outbox/ACK、PC worker 真实媒体门禁与结束收尾、V5 token 与已审查页面结构、图谱人工编辑历史、媒体 PTS/哈希/质量账本。
- 不可继续调用：`candidate_card.v1` 生产/消费、`can_offer_l1`、`VISIT_NO_LONGER_ACTIVE` 作为 L1 拒绝理由、候选 ADB 通知脚本、将 L3/L4 仅以文本展示的业务状态。
- 需在 v2 真机验收通过后删除：旧 CandidateCard 领域与 codec、旧 candidate 通知入口、旧学习路径/SharedPreferences 数据写入。删除前提供迁移回读测试与数据导出，不清理用户未确认的无关脏文件。
- L2 UI 的硬编码 `ContentConceptCanvas` 只可保留为 debug QA fixture；无真实内容图谱时必须显示生成/补全状态，不能展示示例节点冒充结果。
- 当前 `AndroidPcResultInbox` 对图谱 SQLite 与学习内容 SharedPreferences 是两次独立写入；它不得被拿来证明 v2 原子落库。v2 必须在同一 Room 事务完成 package、brief、图谱、通知 outbox、receipt 与去重记录后才 ACK。
- 当前连接页“解除”只调用 token revoke；它没有先停止 MediaProjection、显式等待 PC capture 终止、清理本地控制计划或提供删除结果。v2 解绑必须是一个可恢复的状态机，不是单个按钮回调。

## 6. 当前测试证据的边界

PC 当前 18 个 Python 测试中，至少 11 个仍覆盖 candidate/visit/FusedCandidate；现有 Kotlin 领域测试同样以 `CandidateCard`、`L0_CANDIDATE` 和旧学习路径为主。它们可继续保护旧链迁移期的“不丢证据”性质，但**没有**覆盖 `ContentEpisode`、`RealtimeSemanticFact`、`ContentAnalysisPackage.v2`、`CapturePolicySnapshot`、原子 ACK、短期凭据或 L1 兴趣门。

因此，在 T001–T006、T012–T017、T035–T040 的新测试先失败并转绿前，任何现有绿色测试都只能证明旧候选链未回归，不能证明新系统设计已实现。

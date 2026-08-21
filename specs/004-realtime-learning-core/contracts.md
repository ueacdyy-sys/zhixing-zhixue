# 跨端接口与消息契约

## 1. 传输端口

```kotlin
interface AnalysisTransport {
    suspend fun openSession(request: CaptureSessionRequest): TransportResult
    suspend fun appendBehavior(events: List<BehaviorEvent>): TransportResult
    suspend fun pullDeliveries(cursor: String?): DeliveryPage
    suspend fun acknowledge(receipt: DeliveryReceipt): TransportResult
    val availability: StateFlow<TransportAvailability>
}
```

- `PcLocalModelTransport`：复用现有 PC HTTPS、SPKI pin、pairing、outbox、ACK/NACK；PC 本地模型是配对状态下唯一分析路径。
- `CloudAnalysisTransport`：协议实现与 PC 同构，但必须连接团队自有 HTTPS 网关，不直接把供应商模型密钥写入 APK。真实网关/凭证未配置时只返回 `UNAVAILABLE`。
- `PcSyncForegroundService` 只负责真实媒体运输、PC 会话代次、缓存续传和包投递轮询；不得嵌入兴趣判断、候选卡规则或云端故障切换。每次 `CAPTURE_SESSION_OPENED.v2` 都必须解析唯一 `AnalysisRouteLease`；已配对 PC 的 `PC_BUFFER_ONLY` 只允许同 route 缓存/恢复，绝不把旧缓存提交给云端。

## 2. v2 消息类型

| 方向 | 类型 | 用途 |
|---|---|---|
| Android → 分析端 | `CAPTURE_SESSION_OPENED.v2` | 许可、源、时间基准与会话身份 |
| Android → 分析端 | `BEHAVIOR_BATCH.v2` | 仅上报可观察事实；每项含观测 tier、adapter/证据范围、PTS、episode 归属置信度和授权/前台状态 |
| 分析端 → Android | `L0_FACT_BATCH.v2` | 可持久化、可重放的 L0 事实、质量、水位和证据定位；UI 仅投影其持久化状态 |
| 分析端 → Android | `CONTENT_GRAPH_REVISION.v2` | L0 新事实、PC 模型或联网检索形成的可追溯内容图谱修订 |
| Android → 分析端 | `STUDENT_GRAPH_PATCH.v2` | 学生对 AI 基图的改名、批注、关系增删、隐藏或纠错 |
| 分析端 → Android | `CONTENT_ANALYSIS_PACKAGE.v2` | 唯一的 L1 内容真源：首次修订携带 `briefId` 与 L1 简报，后续修订增量补充图谱、题目和论证 |
| Android → 分析端 | `DELIVERY_RECEIPT.v2` | Android 事务持久化/通知状态/学生操作回执 |

所有消息必须具备 `schemaVersion`、`messageId`、`learnerId`、`sessionId`、`consentId`、`consentGeneration`、`policyBundleHash`、`protocolProfileId`、带时区创建时间、幂等键和结构化错误码。涉及敏感信息、未成年人、云端或导出的 envelope 还必须带 `processingEligibilityGrantId`；普通 capture consent 不可替代。`learnerId` 是 envelope 的授权主体，并与 token、session、所有 payload ID 和 receipt 做服务端一致性校验；任何不匹配直接拒绝。接收端在解析前、事务内、产生 ACK/通知/patch 副作用前都必须比对当前 `ConsentFence`、`ProcessingEligibilityGrant`、`PolicyBundle` 与 `ProtocolCompatibilityProfile`；旧 generation、tombstone、无效/过期 grant、无效 bundle 或不兼容 schema 一律拒绝且不得 ACK 为成功。`episodeId` 只在已归属 episode 的消息中必填；行为批次允许未知归属，但每个事件必须明确 `attributionState`，未知或 `EPISODE_AMBIGUOUS` 归属事件绝不进入兴趣评估。边界解析采用严格 schema 校验；未知字段可保留，未知必填语义不可假定成功。

`L0_FACT_BATCH.v2` 必须含 `batchId`、fact id、episode/scope 归属或未知状态、PTS/时钟水位、质量、证据 locator、`inferenceProvenanceId`、输出哈希和幂等键。行为事实还必须给出 learner/session/source/capture-consent/generation、`EpisodeAttributionState`、证据 PTS 范围、单调观察/到期时间、`ObservationTier`、注册 `adapterId`/版本、前台快照、不可复用 action attestation、scope relation/lineage 与可回放证据范围；没有 `VERIFIED_PLAYER + progressEvidenceId` 不得发出精确进度事实。Android/PC 都必须持久化并 ACK 后才可投影到 UI；它不是瞬态横幅。

不存在独立的 `L1_LEARNING_BRIEF.v2` 入站消息：`L1LearningBrief` 仅为 `CONTENT_ANALYSIS_PACKAGE.v2.l1` 的嵌入对象。首次包必须包含 `packageId`、不可变 `packageRevisionId`、`episodeId`、`semanticScope`、`LearningMoment + LearningMomentRevision`、`evidenceSufficiencyProfileId`、`runtimeSemanticRisk=CLEAR`、`inferenceProvenanceId`、`interestAssessment`、`learningOfferAssessment`、`l1.briefId`、`l1.learningMomentId`、稳定 `l1.l1InterventionKey` 与 L1 证据；Android 以 `briefId` 作为路由和交互回执主键，通知以 moment intervention key 去重。

`CONTENT_GRAPH_REVISION.v2` 额外要求 `revisionId`、`parentRevisionId?`、`origin`、节点/边操作、`claimStatus` 和 `knowledgeSources[]`。`PC_WEB_RESEARCH` 的每一个关系必须回指来源；来源冲突时保留两个带状态的主张，不以“最后一次模型输出”覆盖原图。`STUDENT_GRAPH_PATCH.v2` 只记录学生覆盖层，不能改写 AI 原始证据。任何 revision/patch/ACK 必须同时验证其 `learnerId + packageId + revisionId` 归属，不能以全局 revision 或 brief ID 直接读取。

## 3. 通知契约

```json
{
  "notificationId": "notice_...",
  "notificationAttemptId": "attempt_...",
  "briefId": "brief_...",
  "learningMomentId": "moment_...",
  "level": "L1",
  "title": "AI 已从内容包生成的概念标题",
  "body": "低打扰摘要",
  "deepLink": "zhixing://l1/brief_...?attempt=...&nonce=...",
  "dedupeKey": "l1:<learnerId>:<momentId>:NORMAL",
  "dispatchGeneration": 12,
  "tombstoneGeneration": 3,
  "deviceDispatchNonce": "single-use-short-lived",
  "lockscreenDisclosure": "MINIMAL",
  "actionNonce": "unguessable",
  "deliveryContextSnapshotId": "ctx_..."
}
```

Android 以 `IMPORTANCE_HIGH` 和 MessagingStyle 尝试发出通知。普通通知的稳定去重键固定为 `l1:<learnerId>:<momentId>:NORMAL`，不得含 scope hash、package revision 或 interest assessment；图谱补全、scope/package/兴趣修订或重投均不得新增普通通知额度。通知 outbox 的 worker 领取 `NotificationAttempt` 后必须获得短 lease 与 Android 本机签发的一次性短时 `deviceDispatchNonce`，并在 `notify()` 前后比较 nonce、`dispatchGeneration/tombstoneGeneration`、`ConsentFence`、正式作答 fence、attempt status 和未过期的 `DeliveryContextSnapshot=SAME_SCOPE | CONTINUOUS_SAME_EPISODE`；后者还须验证同 episode PTS 连续、概念 lineage 相关、前台有效和归属可信。任何失败消费 nonce 并抑制该 attempt，不可重投为新通知；同一 episode 的普通 L1 intervention 必须受唯一预算限制。点击/稍后/删除 receiver 使用 `notificationAttemptId + actionNonce + learnerId` 校验，事件优先级固定为 `CANCELLED_REVOKED > OPENED > DEFER_BY_USER > DISMISSED`。点击深链由 `BriefAccessResolver` 定位 `l1/{briefId}`：`ACTIVE` 显示当前版本，`REVISED` 显示修订说明，`WITHDRAWN/EXPIRED/NOT_FOUND/SCOPE_DENIED/STORAGE_PENDING` 显示不泄露内容的对应状态；冷启动 Back 固定返回该 learner 的 Discover，绝不回退样例/旧 fixture。首次 `CONTENT_ANALYSIS_PACKAGE.v2` 的 brief 事务持久化后才允许发通知，后续 package revision 只更新对应 L1 页面。通知执行前检查 `NotificationCapability`：运行时 `POST_NOTIFICATIONS`、全局通知开关、频道重要级别与锁屏可见性；锁屏正文默认 `MINIMAL`，不能暴露源应用、概念、摘要、行为、图谱或原始转写。Android/OEM 仍可能压制 heads-up，故日志必须区分“已提交 NotificationManager”和“指定基准真机人工可见横幅”。通知权限关闭或投递已失去上下文相关性时，L1 仍存在于发现页，只是不发 heads-up。关闭、稍后查看、点击、进入 L2–L4 都写入 `LearningActivity` 并标记 origin：通知提交、自动恢复、深链重建、后台刷新和迁移只能写 `SYSTEM_*`，只有经用户明确动作证据确认的操作可写 `STUDENT_EXPLICIT`；系统 activity 不得进入兴趣、画像或正向二次触达输入。

每次通知投递前和从系统设置返回后都必须刷新 `NotificationCapabilitySnapshot`。权限、应用/频道重要性和锁屏可见性可展示对应的系统设置入口；DND/OEM 压制只能显示原因、保留 Discover，不能自动绕过、自动打开设置或反复催促。日志必须区分“已提交 NotificationManager”和“指定基准真机人工可见横幅”。

## 4. 错误语义

| 错误码 | 处理 |
|---|---|
| `AUDIO_REQUIRED_UNRESOLVED` | 保留 L0、请求/等待音频恢复；不开放 L1 |
| `AUDIO_ABSENCE_UNVERIFIED` | 仅有无音轨/absence proof，缺 scope 级语义非必要和视觉/文字覆盖证明；保持 L0 |
| `SEMANTIC_INCOMPLETE` | 保留 L0 与缺口；不生成内容包 |
| `PC_UNAVAILABLE` | 只缓存并展示恢复状态；配对 PC 会话不切云 |
| `PC_BUFFER_RESUME_REJECTED` | manifest 的 sequence、PTS、hash、ACK cursor、generation 或幂等键不一致；隔离缓存，不跨 gap 续传 |
| `LATE_FACT_REASSESS_REQUIRED` | late fact 已准入但尚未形成 revision/withdraw；不得直接更新 watermark、图谱或通知 |
| `SEMANTIC_LEDGER_CONFLICT` | fact idempotency、scope predecessor/hash/revision、presentation 或 late admission 与不可变账本不一致；拒绝写入与任何 L1 副作用 |
| `CLOUD_UNAVAILABLE` | 无 PC 模式下明确失败，不伪造包/通知 |
| `PACKAGE_VALIDATION_FAILED` | NACK 并入审计 dead letter；不写半包、不发通知 |
| `CONTENT_PACKAGE_GATE_DENIED` | scope/兴趣/offer/route/音频/风险/证据/修订任一硬门不符；不持久化、不 ACK、不创建通知 |
| `NOTIFICATION_BLOCKED` | 包已经 ACK 并保留；仅更新独立通知 outbox 状态 |
| `PERMISSION_REVOKED` | 停止采集/传输并执行授权范围内删除审计 |
| `EPISODE_AMBIGUOUS` | 隔离 L0 质量事实；不得进入兴趣、L1、图谱合并或个人索引 |
| `AUDIO_CAPTURE_RESTRICTED` | 显示能力/限制原因；关键语义未覆盖时保持 L0，不以无声内容替代 |
| `MEDIA_SECURITY_REJECTED` | 拒绝媒体分片、撤销 session；不得回退明文或弱认证 transport |
| `SAFETY_INTERVENTION_BLOCKED` | 内容仅记录或进入人工复核；不得创建 L1 heads-up |
| `PROCESSING_ELIGIBILITY_UNAVAILABLE` | 适用处理资格缺失、过期或撤销；对应路径不得采集外发、恢复、投递或导出 |
| `CUTOVER_GATE_DENIED` | v2 未达到指定灰度/发布门；旧链只能只读，绝不回退到 candidate 通知 |
| `NOTIFICATION_CAPABILITY_BLOCKED` | 记录阻断层和可用设置入口；不绕过用户/DND/OEM 控制，Discover 保留 |
| `INFERENCE_PROVENANCE_INCOMPLETE` | 产物仅可作不可复现记录；不得进入 L1/L3/L4、导出或能力声明 |
| `MODEL_CAPABILITY_VIOLATION` | 输入试图升级工具/网络/控制权限或 worker 越权；隔离任务并停止副作用 |
| `STUDENT_ACTION_CONFIRMATION_REQUIRED` | 助手只能展示逐次确认 proposal；未确认不得执行任何动作 |
| `SAFETY_CIRCUIT_OPEN` | 受影响范围停止 L1/L3/L4/通知/导出；只保留最小 L0 审计和删除路径 |
| `OBSERVATION_UNVERIFIED` | 不生成精确进度结论；可按 profile 保留弱线索或显示未知 |
| `RUNTIME_SEMANTIC_ABSTAIN` | 当前 scope 只保留 L0 质量/缺口；不得创建 L1 或用后续结果改写旧拒绝 |
| `DELIVERY_CONTEXT_STALE` | 保留 brief 到发现页；通知改为 deferred/suppressed，不补发 heads-up |
| `RESOURCE_GOVERNOR_PAUSED` | 显示节流/暂停原因与恢复动作；不得静默丢弃或称实时 |
| `SEMANTIC_HEARTBEAT_EXPIRED` | capture 仍可继续但 L0 理解已停滞；禁止新 L1，等待连续且达标的新 watermark |
| `ANALYSIS_ROUTE_LEASE_DENIED` | session route 不是当前 owner，或 PC 缓存试图出域；拒绝媒体/行为/包副作用 |
| `PROCESSING_ELIGIBILITY_UNAVAILABLE` | 适用处理资格缺失、过期或撤销；对应路径不得采集外发、恢复、投递或导出 |
| `CUTOVER_GATE_DENIED` | v2 未达到指定灰度/发布门；旧链只能只读，绝不回退到 candidate 通知 |

## 5. 兼容与迁移

`candidate_card.v1`、`PcKnowledgeAnalysisResult`、`CandidateCardMessageCodec` 只保留只读迁移适配器。新页面、通知、PC outbox 和新测试不得再生产或消费它们。即日起 `candidate_notice_dispatcher.py` 和 `CandidateNoticeReceiver` 均不得拥有 production dispatch entry；迁移完成后才能删除旧 codec/SharedPreferences 仓库及剩余只读适配器。

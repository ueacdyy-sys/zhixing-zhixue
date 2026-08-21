# 领域数据模型与不变量

## 1. 领域对象

| 对象 | 责任 | 关键字段 |
|---|---|---|
| `ContentEpisode` | 从连续屏幕/第一视角流中推断的同一内容单元；不伪造平台视频 ID | `episode_id`、`learner_id`、`source_kind`、`capture_session_id`、consent generation、PTS/`continuity_start_pts` 范围、`boundary_confidence`、`boundary_reason`、resolver/policy 版本、状态 |
| `LearningMoment` | episode 内一次可学习、可进入 Discover 的概念/观点/事件锚点；不等于媒体 episode、图谱 revision 或通知 attempt | `moment_id`、learner/session/source/consent、`episode_id`、semantic lineage、稳定 `learning_anchor_id`、稳定 `intervention_key`、当前 moment revision、状态、创建时间、策略版本 |
| `LearningMomentRevision` | 一个 LearningMoment 在某个稳定 scope 上的不可变 L1/Discover 投影；修订不能创建新的普通通知预算 | `moment_revision_id`、`moment_id`、revision/predecessor、anchor scope/hash/revision、interest/offer assessment、package/brief、证据 hash、修订原因、时间 |
| `LearnerScope` | 本地或云端的学生数据归属边界，不以设备 ID 冒充用户身份 | `learner_id`、local/cloud 模式、认证 subject?、设备绑定、创建/撤销状态 |
| `AssessmentSession` | 正式作答、教材或纸笔任务的只记录会话；只有明确结束收据才可解开干预 fence | `assessment_id`、learner、mode、任务/题目资源版本、状态、开始/暂停/恢复、close reason、closed by、submittedAt、closure receipt、授权、review 状态 |
| `CurriculumResource` | 受控的题目、教材、知识点、答案/评分点资源 | `resource_id`、subject/grade、版本、许可证、知识点、标准答案/评分点、出处 |
| `EvidenceCard` | 复盘或学习承接的可解释证据单元 | `card_id`、session/episode、事实 refs、解释 claims、反证/缺口、置信度、复核、建议动作 |
| `StateSignalWindow` | EEG/手表的质量、连续性、伪迹和非诊断趋势线索 | `window_id`、source、时间范围、质量、伪迹、时钟不确定度、趋势摘要 |
| `ControlledEvidenceExport` | 面向授权复核的最小化、可撤回证据导出 | `export_id`、learner/session、发起/接收方、用途、字段 allowlist、到期、撤回/receipt |
| `SemanticScope` | episode 内已形成稳定语义闭合的连续范围；L1 的最小内容单位 | `scope_id`、`episode_id`、PTS 范围、`scope_hash`、完整度、稳定状态、语义修订、事件时间水位、证据/质量策略/policy/provenance 引用、前代 scope/hash |
| `SemanticQualityPolicy` | 版本化的语义/L1 校准与回归门 | `policy_id`、输入类型、模型/提示版本、标注集版本、指标、通过状态、失效原因 |
| `RealtimeServiceLevelPolicy` | 设备—模型配置可称为实时的可验收门 | `policy_id`、设备/模型配置、持续输入、样本量、p95/max、队列/吞吐阈值、过载动作、批准报告 |
| `L0SemanticHeartbeat` | 证明 L0 仍在按已批准实时策略推进，而不是 capture 存活但推理停滞 | `heartbeat_id`、learner/session/route epoch、last ACK fact/watermark、observed monotonic time、deadline、SLO/profile、状态 |
| `RealtimeSemanticFact` | L0 的不可变增量语义与质量事实；重放只能幂等，不可改写 | `fact_id`、idempotency key、learner/session/episode/source/consent generation、PTS 范围、fact kind/content hash、证据 hash、semantic policy/provenance |
| `BehaviorEvent` | 学生真实可观察行为事实；显式操作与可回放的分析观测必须区分，系统投递永远不是正向兴趣 | `event_id`、origin、learner/session/source/capture-consent/generation、`episode_id?`+`EpisodeAttributionState`、证据 PTS 范围、单调观察/到期时间、adapter/version、action attestation 或 `observation_id`、前台快照、观测 tier/进度证据、scope relation/lineage |
| `ObservationCapability` | 声明当前设备/内容是否实际能观测播放进度、结束、倍速、Seek 或阅读完成 | `capability_id`、episode/source、可观测字段、依据、置信等级、未知原因 |
| `EvidenceSufficiencyProfile` | 按内容类型声明语义完整与兴趣判断实际需要的模态、替代证据和禁止替代项，避免把所有传感器变成统一死门 | `profile_id`、内容类型、所需模态、允许的替代证据、进度证据等级、最小连续范围、禁止推断、版本、批准状态 |
| `RuntimeSemanticRiskAssessment` | 单个实时窗口在已通过离线回归后仍可能出现的未知领域、模态冲突或证据不足风险 | `risk_id`、episode/scope、风险类别、证据缺口、模型/规则版本、结果、拒绝原因、复核状态 |
| `DeliveryContextSnapshot` | L1 投递瞬间学生是否仍处于当前内容或连续语义上下文的可审计快照 | `snapshot_id`、learner/device、brief scope/current scope、`context_relation`、PTS continuity、concept lineage、context nonce、前台/锁屏状态、采样时间、有效期、归属置信度 |
| `ResourceGovernorSnapshot` | 手机和 PC 在每段实时链中对电量、热、存储、网络和推理队列的统一资源决定 | `snapshot_id`、session、设备/模型、battery/thermal/storage/network、queue、决策、降级理由、恢复条件、时间 |
| `AudioSupportMatrixEntry` | 目标设备—Android 版本—内容应用组合下播放音频的真实支持与恢复路径 | `entry_id`、设备/系统/应用版本、audio capability、限制原因、已验证路径、恢复动作、样本/时间、失效状态 |
| `InferenceProvenance` | 使 L0、L1、L2、L3/L4 与竞赛结论可复现的推理配置事实 | `provenance_id`、模型权重/提示词/预处理/采样/解码 hash、硬件/运行时、输入范围、policy/profile、随机性控制、输出 hash、时间 |
| `ModelExecutionCapability` | 模型在媒体理解、检索和助手路径中被授予的最小工具/网络/动作能力 | `capability_id`、worker kind、允许输入、允许工具、网络/凭据/设备/导出权限、policy hash、状态 |
| `StudentActionProposal` | 助手给学生的操作建议及其逐次、可见、scope-bound 确认，而非自动代办 | `proposal_id`、learner/scope、建议动作、目标类别、理由、允许范围、确认/拒绝 receipt、过期、执行状态 |
| `EvaluationDatasetManifest` | 语义质量、算法和竞赛评价数据的许可证、切分和泄漏防线 | `manifest_id`、数据来源/许可证、脱敏、episode/learner/device split、冻结 test set、标注协议、使用版本、撤回状态 |
| `SafetyCircuitBreaker` | 质量、安全、完整性或错误触达事故发生时停止介入的版本化总闸 | `breaker_id`、scope/config、触发指标/事件、状态、影响能力、批准/恢复 receipt、policy version、时间 |
| `AudioCapabilitySnapshot` | 声明播放音频是否可合法且可对齐地采集，不以失败伪装无声 | `snapshot_id`、learner/session/source/consent generation、PTS 范围、采集能力/限制、source fragment hash、clock domain、同步样本/误差/策略上限、absence proof、故障码、策略版本 |
| `SemanticAudioRequirementDecision` | 证明一个 scope 的视觉/文本覆盖使音频确实不是必要语义；不能由无音轨采集事实替代 | `decision_id`、learner/session/source/consent generation、scope/hash、PTS、snapshot ref、requiredness、视觉/文字覆盖 hash、音频非必要证据、policy/trace hash |
| `PcBufferedFragment` / `PcBufferResumeReceipt` | 证明配对 PC 中断后媒体先持久化、可幂等重传且缺口可见；不替代 route owner 授权 | session/consent/route/capture epoch、fragment sequence/PTS/media/local-storage hash、outbox/replay key、manifest、ACK cursor、resume attempt、gap disposition |
| `LateFactAdmission` | 后到 L0 事实的准入与重评意图，不直接写 L1、watermark 或图谱 | fact/source/consent/PTS、base scope revision/hash、watermark/allowed lateness/policy、content/evidence hash、idempotency key、presentation revision ref、disposition |
| `MediaSecuritySession` | 绑定真实媒体 data plane 的加密和双向认证状态 | `session_id`、learner/session、cipher/auth key id、expiry、fragment MAC、anti-replay cursor、撤销状态 |
| `ContentSafetyAssessment` | 约束何时能形成低打扰学习介入，不给风险内容作不当放大 | `assessment_id`、scope、策略版本、分类/最小理由、结果、人工复核状态 |
| `InterestAssessment` | 行为与语义结合后的可解释判定 | `assessment_id`、`episode_id`、`scope_id`、引用事实、策略版本、结果、拒绝原因 |
| `LearningOfferAssessment` | 当前 scope 是否值得生成低打扰学习简报的独立判断 | `assessment_id`、`scope_id`、解释对象类型、学习价值依据、负反馈、策略版本、结果 |
| `L0FactBatch` | 可持久化、可重放的 L0 事实批次 | `batch_id`、`session_id`、事实列表、时钟水位、幂等键、证据定位 |
| `L1LearningBrief` | 一个 LearningMoment 的当前 L1 快照 | `brief_id`、`moment_id`、anchor scope、修订号、解释对象、摘要、证据、关系预览 |
| `ContentAnalysisPackage` | PC/云生成并投递手机的可增量学习内容包 | `package_id`、`episode_id`、`moment_id`/moment revision、修订号、L1 简报、L2 图谱、L3/L4 内容、证据引用 |
| `ContentGraphRevision` | 围绕 LearningMoment 渐进生长的内容图谱修订；可引用同 episode 其他事实但不得自动触达 | `revision_id`、`package_id`、`episode_id`、`moment_id`、父修订、来源、节点/边、证据/引用、完整度 |
| `StudentGraphPatch` | 学生对 AI 基图作出的可追溯覆盖与批注 | `patch_id`、`revision_id`、操作、目标节点/边、操作者、替代修订 |
| `PersonalEvidenceIndex` | 长期但可撤销的学生主动学习证据索引 | `evidence_id`、用户动作、`package_id`、`patch_id?`、时间、撤回状态 |
| `KnowledgeSource` | 可追溯的外部或内容内知识来源 | `source_id`、URL/标识、检索时间、证据摘录、可信度、检索/模型版本 |
| `LearningActivity` | 学生对 L1–L4 的进入、保存、答题、论证回执 | `activity_id`、`learner_id`、origin、`brief_id`、`package_revision_id`、`graph_revision_id?`、`question_id?`、`question_validation_id?`、`submission_id?`、动作、结果、幂等键、同步状态、时间 |
| `NotificationAttempt` | 一次可线性化、可撤销且本机复核的系统通知投递尝试 | `attempt_id`、learner/brief、notification key、dispatch/tombstone generation、lease、`deviceDispatchNonce`/到期、锁屏披露等级、action nonce、状态、因果事件、时间 |
| `NotificationCapabilitySnapshot` | Android 当前是否实际可能显示 L1 heads-up 及学生可用的修复路径 | `snapshot_id`、learner/device、permission、app/channel importance、lockscreen、DND/OEM 状态、可修复 action、采样时间、有效期 |
| `InterruptionFeedback` | 用户对通知/主题/触达方式的可撤销反馈 | `feedback_id`、来源 brief/通知、作用域、行为、原因、到期/撤销时间 |
| `InterruptionPolicy` | 决定是否立即、延后或只留发现页的版本化打扰策略 | `policy_id`、版本、时区、安静时段、频率预算、主题相似度、延后期限、二次触达规则 |
| `QuestionValidation` | L3 题目的答案与判分规则的独立校验记录 | `validation_id`、`question_id`、状态、校验类型/主体/版本、答案依据、校验时间、撤销原因 |
| `CurriculumAlignment` | 当前内容/题目与 learner 课程资源的适配依据 | `alignment_id`、learner、subject/grade、resource/version、concept refs、适配状态、复核理由 |
| `ConsentReceipt` | 采集、联网补全、云端等授权的可审计快照 | `consent_id`、类别、allowlist、范围、时间、撤回状态 |
| `ProcessingEligibilityGrant` | 对敏感信息、未成年人、云端、导出等适用处理路径的可验证资格结论；不把普通 capture consent 当替代物 | `grant_id`、learner scope、处理类别、policy basis、授权主体类型、最小范围、有效期、撤销代次、状态、审计引用 |
| `ConsentFence` | 阻断撤回后所有在途或重放消息的版本栅栏 | `consent_id`、generation、revoked_at、tombstone hash、owner receipts |
| `RetentionPolicySnapshot` | 正常关闭后的本地/PC/云对象保留与清理规则 | `policy_id`、版本、对象类别、到期时间、合法保留理由、清理状态 |
| `PolicyBundle` | 可验证、可撤销的运行策略集合 | `bundle_hash`、签名/批准者、有效期、最低协议版本、策略版本集合、撤销/回滚代次 |
| `PolicyTrustRoot` | 验证/轮换/紧急撤销策略签名根 | `root_id`、key epoch、public key、签发链、过渡期、撤销状态、最低软件版本 |
| `EvidenceIntegrityLedger` | 证据到结论/删除 receipt 的防篡改可校验链 | `entry_id`、learner/session、parent hash、payload hash、bundle hash、key id、signature、time |
| `LedgerCheckpoint` | 检测账本回滚和跨端锚定的不可变检查点 | `checkpoint_id`、ledger head、monotonic sequence、key epoch、secure-store proof、remote receipt、time authority state |
| `TimeAuthority` | 区分媒体顺序与可信墙上时间的校准来源 | `authority_id`、monotonic anchor、trusted wall-time anchor、uncertainty、source、skew、状态 |
| `CaptureOwnershipLease` | 多设备同源采集的唯一控制权 | `lease_id`、learner/source/session、owner device、epoch、expiry、撤销状态 |
| `AnalysisRouteLease` | 每个 capture session 的唯一分析 route，防止 PC 缓存、云和恢复路径双端处理同一媒体 | `lease_id`、learner/session、consent generation、route state、route epoch、owner endpoint、opened/closed receipt、expiry、撤销状态 |
| `LearnerDeliveryAuthority` | 当前允许接收 L1 系统通知的主手机 | `authority_id`、learner、device、epoch、授予/撤销、有效期、receipt |
| `BackupDeletionManifest` | 删除/恢复链对备份、聚合与密钥的可核对目标 | `manifest_id`、deletion root、object/key/index/backup targets、可读性状态、恢复 fence、receipt |
| `ProtocolCompatibilityProfile` | 客户端/网关/消息 schema 的允许组合 | `profile_id`、最低/最高 schema、能力、弃用期限、拒绝原因、签名 bundle |
| `CapabilityProfile` | 当前设备/learner 可真实声明的能力档位 | `profile_id`、learner/device、档位、必需门状态、证据等级、失效原因、更新时间 |
| `CutoverReleaseGate` | v2 启用、影子验证、只读旧链和安全回退的受控发布状态 | `gate_id`、learner/device、v2 version、legacy mode、shadow scope、通过证据、当前状态、操作者、时间、回退原因 |
| `PairedDeviceCredential` | 手机与 PC 的可撤销设备身份和短期 token 状态 | `device_id`、`key_id`、公钥/Keystore 引用、token 到期、轮换代次、撤销时间 |
| `ScopeTransfer` | 学生明确发起的换机/恢复 scope 迁移 | `transfer_id`、源/目标 learner scope、授权/确认、对象 allowlist、到期、receipt、撤销状态 |
| `UserCaptureIntent` | 学生对 capture/sync 的持久开始、停止与撤回意图 | `intent_id`、source、enabled、原因、发生时间、关联 capture session |
| `FormalAssessmentFence` | 由显式正式作答启动建立、默认覆盖该 learner 全部设备的零介入栅栏 | `fence_id`、learner、assessment、generation、scope=`LEARNER_WIDE`、start/closure receipt、状态、取消/恢复审计 |
| `InterruptionSafetyContext` | 当前是否允许实际打扰的瞬时、可审计上下文 | `context_id`、learner、session mode、lock/call/quiet/system 状态、fence、决策、有效期 |
| `CapturePolicySnapshot` | 每次 MediaProjection 的用户选择范围、来源过滤与失败关闭规则 | `policy_id`、capture scope、允许目的地、过滤版本、未知/敏感决策、同意引用 |
| `DeletionJob` | 跨端删除与撤回的可重试级联任务 | `job_id`、根 consent/session、目标、状态、tombstone、deadline、重试/升级原因、Android/PC/云回执 |
| `EvidenceLocator` | 可跨端且受授权的证据引用 | 内容哈希、owner、resolver、scope token、expiry、脱敏级别、可用性 |
| `PCLearningSession` | PC 自主学习或纸笔/教材的独立入口 | `session_id`、任务、来源适配器、授权、时钟域、学习活动 |

## 2. 核心枚举

```text
SourceKind = PHONE_SCREEN | GLASSES_FIRST_PERSON | PC_LEARNING | PAPER_TEXTBOOK
LearningSessionMode = DAILY_INTEREST | FORMAL_ASSESSMENT | POST_ASSESSMENT_REVIEW
EpisodeStatus = OPEN | GAP_DETECTED | EPISODE_AMBIGUOUS | CLOSED
CaptureState = CAPTURE_PENDING_ANALYSIS | L0_SEMANTIC_ACTIVE | SEMANTIC_STALLED | BACKLOGGED | BACKPRESSURE_PAUSED | NOT_REALTIME | CLOSED | REVOKED | DELETING | DELETED
SemanticCompleteness = IN_PROGRESS | AUDIO_REQUIRED_UNRESOLVED | AUDIO_NOT_REQUIRED | INCOMPLETE | WINDOW_COMPLETE | EPISODE_COMPLETE
SemanticScopeStability = TENTATIVE | STABLE | REVISED | INVALIDATED
InterestResult = NOT_READY | INTEREST_CONFIRMED | REJECTED | EXPIRED
OfferResult = NOT_OFFERABLE | OFFERABLE | SUPPRESSED | REVOKED
PackageDeliveryStatus = PENDING | RECEIVED | PERSISTED | ACKED | DEAD_LETTER
NotificationStatus = PENDING | POSTED | BLOCKED_PERMISSION | BLOCKED_CHANNEL | DEFERRED | SUPPRESSED_CONTEXT | OPENED | DISMISSED | CANCELLED_REVOKED
InterruptionDecision = NOTIFY_NOW | DEFERRED | SUPPRESS_HEADS_UP_KEEP_IN_DISCOVER | CORRECTION_NOTIFY
DeletionState = ACTIVE | TOMBSTONED | DELETE_PENDING | DELETE_ACKED | DELETE_FAILED | DELETE_ESCALATED
ContentGraphOrigin = L0_FACT | PC_MODEL | PC_WEB_RESEARCH | CLOUD_MODEL
LearningMomentStatus = ACTIVE_DISCOVER | REVISED | WITHDRAWN | TOMBSTONED
LearningLevel = L0 | L1 | L2 | L3 | L4
StudentGraphPatchOperation = RENAME_OVERRIDE | NOTE | ADD_EDGE | REMOVE_EDGE | HIDE_SUGGESTION | CORRECT_RELATIONSHIP
GraphClaimStatus = PROPOSED | SUPPORTED | CONFLICTED | WITHDRAWN
QuestionValidationStatus = UNVERIFIED | VERIFIED_BY_RULE | VERIFIED_BY_SOURCE | REJECTED | REVOKED
QuestionPublishState = DRAFT | PUBLISHABLE | PUBLISHED | WITHDRAWN
LearningActivityOrigin = STUDENT_EXPLICIT | SYSTEM_DELIVERY | SYSTEM_RESTORE | SYSTEM_MIGRATION
BehaviorOrigin = STUDENT_EXPLICIT | ANDROID_OBSERVED | ANALYSIS_OBSERVED | SYSTEM_DELIVERY | SYSTEM_RESTORE | SYSTEM_MIGRATION
CurriculumAlignmentState = ALIGNED | NOT_ALIGNED | NEEDS_REVIEW | REVOKED
AudioCaptureState = VERIFIED_PLAYBACK | VERIFIED_MICROPHONE | MIXED_AUDIO | CAPTURE_RESTRICTED | SYNC_UNRESOLVED | UNKNOWN
MediaSecurityState = NEGOTIATING | AUTHENTICATED | EXPIRED | REVOKED | REJECTED
ContentSafetyResult = LEARNING_SAFE | RECORD_ONLY | REQUIRE_HUMAN_REVIEW | BLOCK_INTERVENTION
PolicyBundleState = ACTIVE | EXPIRED | REVOKED | INVALID_SIGNATURE | INCOMPATIBLE
EvidenceIntegrityState = VERIFIED | BROKEN | UNKNOWN | QUARANTINED
TimeAuthorityState = TRUSTED | DEGRADED | UNTRUSTED | UNKNOWN
BriefAccessState = ACTIVE | REVISED | WITHDRAWN | EXPIRED | NOT_FOUND | SCOPE_DENIED | STORAGE_PENDING
L3AnswerReconciliationState = DRAFT | LOCALLY_RECORDED_PENDING_RECONCILIATION | FINALIZED | REJECTED_REVOKED
L4SubmissionDeliveryState = DRAFT | QUEUED | DELIVERED | REJECTED
AssessmentSessionState = DRAFT | ACTIVE | SUSPENDED | SUBMISSION_PENDING | SUBMITTED | ENDED_CONFIRMED | REVIEW_READY
DeviceCredentialState = ACTIVE | EXPIRED | ROTATED | REVOKED
CaptureScopeMode = SYSTEM_SINGLE_APP | WHOLE_SCREEN
CapturePolicyDecision = ALLOW_AUTHORIZED_DESTINATION | PAUSE_PENDING_USER | BLOCK_TRANSPORT | REVOKE
ProgressEvidenceKind = DIRECT_PROGRESS_OBSERVED | WEAK_ATTENTION_SIGNAL | UNKNOWN
ObservationTier = VERIFIED_PLAYER | SCREEN_INFERRED | UNKNOWN
RuntimeSemanticRiskResult = CLEAR | ABSTAIN_L0_ONLY | REQUIRE_REVIEW
DeliveryContextState = SAME_SCOPE | CONTINUOUS_SAME_EPISODE | STALE | UNKNOWN
ResourceDecision = NORMAL | DEGRADED_L0_ONLY | THROTTLED | PAUSE_PENDING_USER
AnalysisRouteState = UNAVAILABLE | PC_LOCAL_ACTIVE | PC_BUFFER_ONLY | CLOUD_ACTIVE | CLOSED | REVOKED
ProcessingEligibilityState = ELIGIBLE | UNAVAILABLE | REVOKED | EXPIRED
CutoverState = LEGACY_READ_ONLY | V2_SHADOW_L0 | V2_ACTIVE | V2_DELIVERY_DISABLED
SafetyCircuitState = CLOSED | OPEN_L0_ONLY | OPEN_ALL_DELIVERY_DISABLED | RECOVERY_PENDING
StudentActionExecutionState = PROPOSED | CONFIRMED | REJECTED | EXPIRED | EXECUTED | CANCELLED
```

`CANDIDATE_ONLY` 仅可作为旧链迁移期的兼容标记，不能出现在新 L0/L1 领域门、通知门或页面路由中。

## 3. `ContentAnalysisPackage.v2` 最小结构

```json
{
  "schemaVersion": "content-analysis-package.v2",
  "packageId": "cap_...",
  "packageRevisionId": "caprev_...",
  "replacesRevisionId": null,
  "learnerId": "learner_...",
  "captureSessionId": "capture_...",
  "captureConsentId": "consent_...",
  "consentGeneration": 7,
  "episodeId": "episode_...",
  "learningMoment": {"momentId": "moment_...", "learningAnchorId": "...", "interventionKey": "l1:learner:moment:NORMAL", "revisionId": "moment_revision_..."},
  "semanticScope": {"scopeId": "scope_...", "startPtsNs": 0, "endPtsNs": 0, "scopeHash": "...", "completeness": "WINDOW_COMPLETE", "stability": "STABLE", "eventTimeWatermark": "...", "boundaryResolverVersion": "..."},
  "sourceKind": "PHONE_SCREEN",
  "analysisVersion": "local-model/2026-07-29",
  "semanticCompleteness": "WINDOW_COMPLETE",
  "revision": 3,
  "evidence": [{"startPtsNs": 0, "endPtsNs": 0, "uri": "local://...", "sha256": "..."}],
  "l1": {"briefId": "brief_...", "learningMomentId": "moment_...", "l1InterventionKey": "l1:learner:moment:NORMAL", "scopeId": "scope_...", "title": "...", "summary": "...", "concepts": [], "sourceExplanation": [], "relationshipPreview": [], "evidenceIds": []},
  "extensions": {"l2?": {"graph": {"nodes": [], "edges": []}}, "l3?": {"objectiveItems": []}, "l4?": {"argumentTasks": []}},
  "interestAssessment": {"assessmentId": "interest_...", "result": "INTEREST_CONFIRMED", "policyVersion": "...", "evidenceIds": []},
  "audioCapabilitySnapshotId": "audio_...",
  "mediaSecuritySessionId": "msec_...",
  "learningOfferAssessment": {"assessmentId": "offer_...", "result": "OFFERABLE", "policyVersion": "...", "evidenceIds": []},
  "contentSafetyAssessment": {"assessmentId": "safe_...", "result": "LEARNING_SAFE", "policyVersion": "...", "reasonCodes": []}
}
```

L1 字段、图谱、题目和论证任务都必须能回指 `evidence` 中的时间范围。`WINDOW_COMPLETE` 时可以投递仅含 L1 简报的包；`EPISODE_COMPLETE` 只是整段内容处理完成状态，不是 L1 前置条件。

`L1LearningBrief` 是上述 `CONTENT_ANALYSIS_PACKAGE.v2.l1` 的嵌入领域对象，不是第二种 PC→Android 入站消息。`briefId` 在一次包修订链中稳定且是通知、深链、ACK 关联与 L1 页面主键；`packageId + packageRevisionId` 只标识其容器及不可变内容版本。

唯一 package schema 校验器必须拒绝 candidate/visit/window 字段替代品，并同时校验 stable scope 的 learner/session/consent/revision/hash、同 episode/lineage 的 `LearningMoment + LearningMomentRevision`、`INTEREST_CONFIRMED`、`OFFERABLE`、`runtimeSemanticRisk=CLEAR`、route lease/epoch、L1 evidence hash、音频充分性、稳定 `l1InterventionKey = l1:learnerId:momentId:NORMAL` 和不可变 package revision 链。scope hash、package revision 或 interest assessment 改变不得生成新的普通触达键。`PackagePersistenceReceipt` 只表示 Android 已原子持久化；通知投递不是 receipt 的组成部分，不能由 PC 伪造为已展示。

## 4. 持久化边界

Android 新链以 Room 作为唯一业务事实库。表至少包括：

```text
learner_scopes, episodes, episode_boundaries, capture_sessions, semantic_scopes, semantic_facts, l0_fact_batches, behavior_events,
semantic_quality_policies, semantic_quality_evaluations, observation_capabilities, evidence_sufficiency_profiles, runtime_semantic_risk_assessments, delivery_context_snapshots, resource_governor_snapshots, audio_support_matrix_entries, audio_capability_snapshots, media_security_sessions, content_safety_assessments, interest_assessments,
learning_offer_assessments, l1_briefs, analysis_packages,
assessment_sessions, curriculum_resources, assessment_items, evidence_cards, evidence_card_claims, state_signal_windows,
curriculum_alignments, consent_fences, processing_eligibility_grants, interruption_safety_contexts,
controlled_evidence_exports, export_receipts,
content_graph_revisions, graph_nodes, graph_edges, student_graph_patches, knowledge_sources,
personal_evidence_index, interruption_feedback, interruption_policies, consent_receipts,
deletion_jobs, deletion_receipts, retention_policy_snapshots, evidence_locators, pc_learning_sessions, textbook_evidence,
policy_bundles, evidence_integrity_ledger, capture_ownership_leases, learner_delivery_authorities, backup_deletion_manifests, protocol_compatibility_profiles,
policy_trust_roots, ledger_checkpoints, time_authorities,
capability_profiles,
inference_provenances, model_execution_capabilities, student_action_proposals, evaluation_dataset_manifests, safety_circuit_breakers,
notification_outbox, notification_attempts, notification_capability_snapshots, learning_activities, question_items, question_validations,
l3_answer_records, paired_device_credentials, user_capture_intents, transport_outbox, transport_receipts,
capture_policy_snapshots, dead_letters, legacy_migration_records
```

一次包投递的顺序是：校验 schema → 同一数据库事务写入 episode/scope/LearningMoment/LearningMomentRevision/brief 或 package/图谱/通知 outbox/receipt → 事务成功后立即 ACK PC → 由通知执行器消费 outbox。通知被权限、频道或上下文策略阻断不是包投递失败，不能阻断 ACK。事务失败才不得 ACK。重投使用不可变 `packageRevisionId`；L1 去重使用稳定 `l1InterventionKey = l1:learnerId:momentId:NORMAL`，scope、兴趣和 package 修订通过 moment/package predecessor 链关联，不能重开普通触达。

PC `PackageOutbox` 以 `(packageId, packageRevisionId)` 和 payload hash 幂等入队，`messageId` 全局唯一；只有持有未过期 delivery lease 且 learner/package/revision/message 全匹配的 `PackagePersistenceReceipt` 才能转为 `ACKED`。系统通知状态不在该 receipt 中，不能让“已调用 notify”代替 Android 原子落库 ACK。

现有手写 SQLite 知识图谱可作为迁移源，学生编辑历史必须迁入 `student_graph_patches`；SharedPreferences 仅保留 UI 偏好、配对元数据和非业务开关。

## 5. 不变量

1. 任何 `RealtimeSemanticFact` 均有 learner/session/episode/source/consent generation、PTS 范围、来源和证据索引。相同 idempotency key 的重放必须得到同一 record hash；不同载荷一律拒绝。普通事实才可推进连续 watermark，late fact 不得推进它。
1a. 旧 `FusedCandidate` 若尚需迁移，只能被投影为 `LEGACY_FUSED_WINDOW_EVIDENCE_ONLY` 的 L0 事实，并复核每个 lane artifact hash；该事实本身不能成为 scope、兴趣、图谱、个人索引或 L1 的输入，直至 v2 语义 reducer 重新验证。
2. 任何 L1 通知均有已持久化的 `L1LearningBrief`，不直接引用 candidate/window/visit；L2–L4 字段可在后续 `ContentAnalysisPackage` 修订中为空。
3. `INCOMPLETE`、`AUDIO_REQUIRED_UNRESOLVED` 绝不允许得到 `INTEREST_CONFIRMED` 或 L1 通知；`AUDIO_NOT_REQUIRED` 必须有同范围 `SemanticAudioRequirementDecision=AUDIO_NOT_REQUIRED_VERIFIED`。`NO_AUDIO_TRACK_VERIFIED`、麦克风、混音、absence proof 或播放音频采集失败任一项都不能单独充当该判定。
4. 内容图谱与长期个人画像分离；自动图谱不得静默写入个人画像。
5. L2/L3/L4 的进入和完成均记录为学生主动 `LearningActivity`。
6. PC 断连不能修改 episode 身份、重置 PTS、丢弃已封存数据或转换到云 transport。缓存恢复必须以持久分片 sequence、PTS、媒体/本地落盘 hash、ACK cursor 和幂等键核对；缺序、PTS gap、generation/hash 不符均隔离，不能产生跨 gap stable scope/L1。
7. `InterestAssessment` 只可引用 `episode_id` 非空、归属置信度合格、观测方法获策略允许且发生时采集授权/前台有效的行为事实。
8. `PC_WEB_RESEARCH` 的每个新增节点/边至少引用一个 `KnowledgeSource`，并记录 `GraphClaimStatus`；它不得直接写入长期个人画像。
9. `ContentGraphRevision` 只服务本次内容；只有 `PersonalEvidenceIndex` 才可进入长期知识全览，并且它必须引用学生主动动作或 `StudentGraphPatch`。
10. L1 只可引用 `STABLE` 且非 `EPISODE_AMBIGUOUS` 的 `SemanticScope`，并同时具有 `INTEREST_CONFIRMED`、`LearningOfferAssessment=OFFERABLE`、`ContentSafetyAssessment=LEARNING_SAFE`、有效 `AudioCapabilitySnapshot`、必要时的 `SemanticAudioRequirementDecision` 与已认证 `MediaSecuritySession`；后到冲突事实只能经过 `LateFactAdmission` 形成新修订/撤回或 quarantine，不得推进 watermark、直接投递 L1 或覆写旧证据版本。
11. L3 客观题的答案、解析和可判分规则必须带独立的依据引用与校验状态；`UNVERIFIED` 题目不得发布。
12. `QuestionValidation` 的校验主体不得是该题目的同一次生成器；答案依据、校验器版本或来源被撤销时题目必须转为 `REVOKED/WITHDRAWN`，已有答题记录保留审计但不得再以旧答案判分。
13. `InterruptionFeedback` 必须标明来源（系统阻断、dismiss、稍后、明确不感兴趣、主题屏蔽、撤销）和作用域；系统/OEM 阻断绝不推断为用户负反馈。
14. 每个 `ContentAnalysisPackage` 必须绑定 `captureSessionId + captureConsentId`；许可撤回后该链的所有包、图谱、题目、通知和 evidence locator 均不可读取或投递。
15. 正常关闭不等于无限保留：原始媒体、缓存、转写、事实、派生包和审计回执均必须绑定 `RetentionPolicySnapshot`；到期清理与撤回删除都产生可审计结果。
16. `PairedDeviceCredential` 的私钥不可导出；短期 token 不得替代设备身份。`REVOKED` 或用户停止时，任何未结算 capture、outbox、lease 和 enrichment 都不得继续运行或在服务重启后恢复。
17. MediaProjection 不能被伪装为平台视频 ID 或来源识别。每个 capture session 必须绑定 `CapturePolicySnapshot`：用户通过系统 UI 选择的 `SYSTEM_SINGLE_APP` 或 `WHOLE_SCREEN` 范围、可发送目的地与未知/敏感画面的失败关闭决策。无法可靠判定时只可 `PAUSE_PENDING_USER/BLOCK_TRANSPORT`，不得继续外发或猜测来源。
18. `DIRECT_PROGRESS_OBSERVED` 必须引用可复核的进度/结束证据范围；`WEAK_ATTENTION_SIGNAL` 与 `UNKNOWN` 不得生成“看完、覆盖比例、倍速完成、自然结束”事实，也不能独自得到 `INTEREST_CONFIRMED`。
19. `WINDOW_COMPLETE` 与 L1 必须引用已通过的 `SemanticQualityPolicy`；模型自报 confidence、检索排名或单次人工演示不构成通过。模型、prompt、模态处理或来源策略变更后，旧通过状态失效直至回归集重新验证。
20. 所有 capture、episode、事实、assessment、package、图谱、个人索引、通知、凭据和删除任务均必须属于单一 `learnerId`；主键、去重键、outbox lease 和 evidence locator 都以 learner scope 隔离。设备 ID、PC pairing token、RTSP URL 或 IP 地址不得作为学生身份。local scope 不自动上传/合并；cloud scope 必须由显式认证 subject 和单独 consent 创建。
21. 撤回/删除任务必须有 policy-owned deadline、每个目标的 receipt 与终态。逾期或不可重试错误转 `DELETE_ESCALATED` 并在应用内治理状态可见；已 `POSTED` 的 L1 系统通知必须通过其 Android notification key 取消，深链与缓存读取同时失效，不能只删除发现页记录。
22. `FORMAL_ASSESSMENT` 期间绝不创建/执行 L1 notification、悬浮窗、练习、答案、提示或即时纠错 outbox；只有会话结束后可创建 `POST_ASSESSMENT_REVIEW` 证据卡。`StateSignalWindow` 只能降低/提高证据质量或标记伪迹，不能单独产出学习、专注、能力、医学或心理结论。
23. `EvidenceCard` 的每一条解释必须回指事实 refs 或受控 `CurriculumResource`，并显式保存反证/缺口和 review 状态；受控资源的版本、许可证、答案/评分点变更必须生成新 revision，旧题目/证据卡不可静默重写。
24. `ControlledEvidenceExport` 只能在显式授权 scope 内导出字段 allowlist 中的脱敏内容；接收方、用途、到期、撤回和下载/读取 receipt 都是必填。导出绝不赋予长期 live 数据权限，撤回后不可再解析或下载。
25. `ContentEpisode` 处于 `EPISODE_AMBIGUOUS`，或其 `AudioCapabilitySnapshot`、`MediaSecuritySession`、`ContentSafetyAssessment` 任一项未通过时，绝不允许 L1；只可保留不外发的 L0 质量/失败记录。
26. 所有持久化表、外发 envelope、去重键、lease、revision、patch、notification、evidence locator 与删除目标均必须由 `learner_id` 强制隔离；以数据库复合主键/FK 与服务端授权校验实施，不能只依赖 package 的间接关联。
27. `consentGeneration` 必须在 capture session、媒体分片、L0 facts、behavior、package、ACK、patch、outbox 和 deletion receipt 间一致；任何低于当前 `ConsentFence` generation 或已 tombstoned 的消息不得落库、展示、ACK 或触发副作用。
28. `LearningActivityOrigin != STUDENT_EXPLICIT` 的活动不能作为 `InterestAssessment`、`LearningOfferAssessment`、`PersonalEvidenceIndex` 或提醒频率模型的正向输入；学生显式操作也必须与其 scope/episode/brief 可审计绑定。
29. L3 `QuestionItem` 和 `POST_ASSESSMENT_REVIEW` 的课程性结论必须有 `CurriculumAlignment=ALIGNED` 与版本化 `CurriculumResource`；`NOT_ALIGNED/NEEDS_REVIEW/REVOKED` 时不得生成题目、评分、掌握趋势或答案示例。
30. 通知 outbox 必须以 `NotificationAttempt` 的 lease、`dispatchGeneration`、`tombstoneGeneration`、不可猜测 `actionNonce` 和 Android `notificationKey` 线性化。执行器在领取、`notify()` 前后和回调处理时均检查撤回/正式作答 fence；`CANCELLED_REVOKED` 不能被旧 worker、重复 PendingIntent 或进程恢复重新投递。
31. 每个学生活动必须固定其当时的 brief/package/graph/question/validation/submission 不可变版本。修订、撤回、迁移或 scope 变化不得重解释历史活动；新操作必须在显式可访问的当前版本上创建新 activity。
32. 冷启动深链必须经 `BriefAccessResolver` 得到 `ACTIVE/REVISED/WITHDRAWN/EXPIRED/NOT_FOUND/SCOPE_DENIED/STORAGE_PENDING` 之一；拒绝/未就绪状态不得回退到样例、旧 fixture 或其他 learner 内容，返回链固定为该 learner 的 Discover。
33. 离线 L3 只能以 `LOCALLY_RECORDED_PENDING_RECONCILIATION` 保存答案，离线 L4 只能 `QUEUED`；未核对当前 `QuestionValidation`、课程对齐、consent fence 和撤回状态前，不得显示最终成绩、写长期索引或生成掌握结论。
34. 同一 `NotificationAttempt` 的因果优先级为 `CANCELLED_REVOKED > OPENED > DEFER_BY_USER > DISMISSED`；所有 receiver 回调必须按 attempt/nonce 幂等，Android 的 delete callback 不能覆盖更高优先级事件。
35. `PolicyBundle` 是策略真实性的唯一来源；所有使用策略的结论都必须绑定 bundle hash，签名无效、过期、撤销或与 `ProtocolCompatibilityProfile` 不兼容时失败关闭。影响安全/授权/质量/课程适配的 bundle 变更必须重新评估未呈现结果。
36. 可用于 L1/L3/L4/导出/竞赛声明的证据必须有连续、可验签的 `EvidenceIntegrityLedger` 链；链断或验证失败时禁止升级为真实闭环/正式结论。
37. 同一 learner 的同源 capture 必须持有唯一 `CaptureOwnershipLease`，同一 L1 intervention 只能由 `LearnerDeliveryAuthority` 的当前 epoch 投递。旧设备/旧 epoch、重复 source 或 authority 竞争一律失败关闭。
38. `DeletionJob` 的完成必须引用 `BackupDeletionManifest`：备份、灾备副本、聚合、索引和对象密钥要么已删除，要么已不可读且恢复前 tombstone 必应用。未达该状态只能 `DELETE_PENDING/ESCALATED`，不得写删除完成。
39. `AnalysisTransport` 只接受当前 `ProtocolCompatibilityProfile` 允许且已签名 bundle 的 schema/capability 组合；不兼容客户端/网关显示升级/不可用，绝不降级到旧 candidate/card 协议。
40. `PolicyBundle` 的签名只能由当前 `PolicyTrustRoot` 及其有效 key epoch 验证；根轮换/紧急撤销必须可追溯、不可回退，根状态未知/失效时不允许继续处理或投递。
41. `EvidenceIntegrityLedger` 必须由连续 `LedgerCheckpoint` 保护；恢复/换机/重放若不能证明 checkpoint 连续，不得把该链标为 `VERIFIED`。
42. 事件顺序使用单调 PTS/时钟；`TimeAuthority` 的可信墙上时间才可用于保留、token、quiet hours、到期和竞赛延迟。墙上时间不可信时采取不打扰/不误删/可见待处理的保守状态。
43. UI、演示和报告只能读取 `CapabilityProfile` 声称当前档位；代码存在、接口可连、旧缓存、调试开关或单一正例均不能升级档位。档位未通过时显示真实 unavailable/失败状态，不得阻塞已通过的前一档。
44. `EvidenceSufficiencyProfile` 必须按视频、图文、直播及其实际语义模态决定完整性与兴趣证据；不得用固定观看秒数、所有传感器齐备或“缺少任何一种观测”一刀切拒绝 L1。它也不得把采集失败改标为非必要模态，关键语音、边界、安全、授权和完整语义仍是不可放松的硬门。
45. `VERIFIED_PLAYER` 才可产生“自然结束、覆盖比例、倍速或 Seek”精确事实，且必须记录可回放的 adapter/证据范围；`SCREEN_INFERRED` 与 `UNKNOWN` 只能作为 `EvidenceSufficiencyProfile` 明示允许的组合兴趣线索，绝不显示或使用伪造进度结论。
46. 每个将进入 L1 的 scope 必须有 `RuntimeSemanticRiskAssessment=CLEAR`。未知领域、关键模态互相冲突、证据覆盖不足或运行时质量退化时为 `ABSTAIN_L0_ONLY/REQUIRE_REVIEW`；离线回归通过不允许覆盖这个逐窗口弃答门。
47. `NOTIFY_NOW` 必须引用仍有效的 `DeliveryContextSnapshot=SAME_SCOPE` 或 `CONTINUOUS_SAME_EPISODE`。后者额外要求同 learner/episode、PTS 连续、概念 lineage 相关、前台有效和归属可信；它允许学生持续观看同一视频下一窗口时接到该 episode 的一次 L1，不能虚构精确播放进度。快照过期、学生已切换 episode、关系断裂、归属未知或前台不相关时不得补发高优先级通知，只能 `DEFERRED/SUPPRESS_HEADS_UP_KEEP_IN_DISCOVER`；L1 简报本身不丢失。
48. `ResourceGovernorSnapshot` 只能选择明确的 `NORMAL/DEGRADED_L0_ONLY/THROTTLED/PAUSE_PENDING_USER` 路径。资源不足不得静默丢弃已封存媒体、把降采样后的不完整结果写为 L1，或以无限积压继续宣称实时；恢复也必须重新满足当前 SLO、授权和 context 门。
49. `AudioSupportMatrixEntry` 是音频“尽量修复”的真实依据：每个宣称支持的目标应用组合都须有可复现样本和同源同步测量。未知、DRM/应用拒绝或已失效组合只能显示受限原因与恢复动作，不能承诺 100% 采集或使用麦克风替代播放音频。
50. 学生必须能查看某条 L1 使用了哪些行为/语义证据、关闭或撤销哪一类后续打扰、以及撤销自己的 `PersonalEvidenceIndex` 条目；这些控制只改变未来策略和可撤销个人索引，不得篡改原始证据、把系统阻断写成负反馈，或强迫学生公开长期画像。
51. 涉及敏感信息、未成年人、云端分析、受控导出的路径必须引用当前 `ProcessingEligibilityGrant=ELIGIBLE`；它由部署适用的政策决定是否需要何种授权主体，系统不得从设备、年级、历史数据或普通 capture consent 推断资格。grant 过期/撤销/未知时相应 capability 必须停在 `UNAVAILABLE`，在 ingress、任务恢复、投递和导出前后均失败关闭。
52. `CutoverReleaseGate` 只允许 `LEGACY_READ_ONLY → V2_SHADOW_L0 → V2_ACTIVE` 的前进路径。影子阶段只能复用已获许可的同一 evidence locator 生成不投递、不写画像、不发通知的 L0 对照；回退只能进入 `V2_DELIVERY_DISABLED + LEGACY_READ_ONLY`，绝不恢复旧 candidate/visit 通知、兴趣判定或新 JSON 写入。
53. `ProcessingEligibilityGrant` 必须作为 scope-bound 持久化事实，以 `grant_id + learner_id + consentGeneration + status` 约束所有 ingress、任务恢复、通知、云端和导出；进程死亡、离线恢复或跨 scope 消息不得回退到内存缓存或普通 capture consent。
54. `FORMAL_ASSESSMENT_FENCE` 只可由与 assessment 同 scope 的 `SUBMITTED` 或 `ENDED_CONFIRMED` closure receipt 解除。Back、锁屏、前后台切换、进程死亡、网络断开、重复 close 或未确认的离线草稿只将 session 标为 `SUSPENDED/SUBMISSION_PENDING`，不得进入 `REVIEW_READY`、恢复通知、显示答案或开始复盘。
55. 每次通知投递或系统设置返回均应生成 `NotificationCapabilitySnapshot`。权限/频道/锁屏可见性可跳转对应系统设置；DND/OEM 阻断只解释、不可自动绕过或反复催促。无论快照为何，已持久化 L1 始终保留 Discover 入口。
56. 可用于 L0 事实、L1/L3/L4、图谱 claim、导出或竞赛声明的模型产物必须引用不可变 `InferenceProvenance`；模型名称字符串不构成可复现性。权重、prompt、预处理、采样/解码、硬件/运行时、策略/profile、输入范围或随机性设置缺失时，产物只能记录为不可复现，不得形成正式结论或能力声明。
57. 屏幕文本、视频语音、OCR/ASR、网页、附件和模型输出都是不可信数据，不能升级 `ModelExecutionCapability`。媒体理解 worker 默认无网络、无凭据、无设备控制、无导出、无通知投递权限；检索 sandbox 的结果也只能写 L2，不能改变工具权限或 L0/L1 因果。
58. 每个 `L0_SEMANTIC_ACTIVE` session 必须有未过期 `L0SemanticHeartbeat`。last ACK watermark 超出该 SLO policy 的 deadline 时状态必为 `SEMANTIC_STALLED`，禁止创建 L1；新 batch 只有在连续、授权有效且重新符合 SLO 后才能恢复活跃。capture/RTSP 存活、进程存活或旧 watermark 都不能续租 heartbeat。
59. `AnalysisRouteLease` 以 `learner + session + consentGeneration` 唯一约束实时分析 owner。PC 断连只允许 `PC_LOCAL_ACTIVE → PC_BUFFER_ONLY`；云授权、恢复或服务端可用不得变更该 lease。云 route 只能以学生确认的新 session 建立，且旧 PC lease 已关闭、旧缓存禁止出域。
60. `FormalAssessmentFence` 首期固定 `LEARNER_WIDE`，只能由 `ASSESSMENT_START_CONFIRMED` 或受控任务启动 receipt 建立，并以同一 `learnerId + assessmentId + fenceGeneration` 的 closure receipt 解除。模型/画面推断、Back、锁屏、崩溃、断网、其他设备或其他 task 的 close 绝不能建立或解除 fence。
61. 超出策略 gap 后，episode 必须关闭/分裂，或将新的 `continuity_start_pts` 推进到 gap 之后；`SemanticScope.startPts` 不得早于该值。`GAP_DETECTED` 和 gap 前后拼接的 scope 都不能稳定或产生 L1。scope revision 必须带前代 scope id 与 hash，持久化层再以同 learner/episode 的 FK 验证；revision 不能只依赖递增整数自证。
62. `INTEREST_CONFIRMED` 的每个行为事实必须由 `EpisodeAttributionState=RESOLVED` 绑定同一 learner/session/source/capture consent/generation，并包含 PTS 范围、单调到期、已注册 adapter/version 与不可复用的 action attestation。assessment 必须直接绑定稳定 target scope 的 hash/revision/lineage，并按已验签 profile 的独立性门验证；未知/歧义、跨 session/source/consent、过期、重放 event/attestation、scope 外或无播放器时间线证明的行为一律失败关闭。
63. Android 每次 heads-up 必须以一次性、短时 `deviceDispatchNonce` 在本机二次复核当前 context、consent fence、formal-assessment fence、scope relation 与 package revision。复核失败只写 Discover。锁屏默认 `MINIMAL` 披露，不得展示学习概念、摘要、来源、行为或图谱；Android 用户可明确调整可见性，但不能绕过深链访问校验。
58. `StudentActionProposal` 只能建议或在学生明确确认后打开本应用内允许页面；不得经 Accessibility、ADB、隐式 Intent、后台 service 或模型工具调用替学生操作第三方 App、发送消息、修改系统设置或执行不可逆动作。确认必须逐次、可见、可撤销、scope-bound 和可审计。
59. `SemanticQualityPolicy` 的训练/回归/竞赛评测必须引用 `EvaluationDatasetManifest`：按 episode、learner、来源和设备隔离开发/验证/冻结测试，记录许可证、脱敏和标注协议。测试集或同一 episode/learner 的泄漏不得用于阈值、prompt、模型或样本选择；被撤回/无许可数据不能继续训练或作为通过证据。
60. `SafetyCircuitBreaker` 打开时优先停止其范围内 L1/L3/L4、通知、导出或全部投递，保留最小 L0 审计和删除路径；模型不得自行关闭。恢复必须有新 policy、指定样本/根因证据和人工批准 receipt，且在恢复前重新评估未呈现包。

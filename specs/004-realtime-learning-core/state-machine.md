# 关键状态机

## CaptureSession 与权限

```text
CAPTURE_PENDING_ANALYSIS
  → L0_SEMANTIC_ACTIVE       (首个持久 L0_FACT_BATCH 被 ACK)
  → SEMANTIC_STALLED          (L0 semantic heartbeat/watermark 超过策略 deadline)
  → BACKLOGGED | NOT_REALTIME (SLO 水位超限)
  → DEGRADED_L0_ONLY | THROTTLED | PAUSE_PENDING_USER (ResourceGovernor 决定)
  → BACKPRESSURE_PAUSED       (缓存达到 hard limit，等待用户恢复)
  → CLOSED                    (正常停止)
  → REVOKED → DELETING → DELETED (授权撤回或删除请求)
```

- 正常 `CLOSED`：停止新媒体，已获许可的封存任务按保留策略结算。
- `REVOKED`：立即停止采集、分析、重试、联网补全与通知投递；删除协议优先。
- 缓存达到上限：进入 `BACKPRESSURE_PAUSED`，提示用户并保留已有封存数据；不得无声覆盖或丢弃。
- `DEGRADED_L0_ONLY` 只能产出质量/缺口事实；`THROTTLED` 必须记录输入、处理率与恢复条件；`PAUSE_PENDING_USER` 等待学生处理电量、热、存储或网络提示。`SEMANTIC_STALLED` 表示媒体 capture 未必停止，但最后 L0 watermark 已过期：禁止新 L1，UI 必须明确区分 capture 与理解状态。四者恢复时重新校验 SLO、许可和当前 context，不能从旧积压直接投递 L1。

## 分析路由所有权

```text
UNAVAILABLE → PC_LOCAL_ACTIVE → PC_BUFFER_ONLY → PC_LOCAL_ACTIVE
UNAVAILABLE → CLOUD_ACTIVE
```

- `AnalysisRouteLease` 绑定 learner、session、consent generation、route epoch 与唯一 owner。一个 session 同时只能有一个 `PC_LOCAL_ACTIVE/PC_BUFFER_ONLY/CLOUD_ACTIVE` route。
- PC 断连只能 `PC_LOCAL_ACTIVE → PC_BUFFER_ONLY`，缓存仍属于该 PC route；云资格到达、服务恢复或重连不得隐式切换。
- `PC_BUFFER_ONLY → CLOUD_ACTIVE` 不存在。学生必须显式结束旧 session，取得旧 lease 关闭 receipt，再确认创建新的云 session/route；任何旧缓存不得被云读取或外发。

## ContentEpisode 与 SemanticScope

```text
Episode: OPEN → GAP_DETECTED → CLOSED | EPISODE_AMBIGUOUS → CLOSED
Scope: TENTATIVE → STABLE → REVISED | INVALIDATED
```

- 内容边界无法确定时分裂为新 episode 或标记 `EPISODE_AMBIGUOUS`，不合并不确定来源；该状态只保留 L0 质量事实，不能形成兴趣、L1 或图谱合并。
- PTS epoch 重置、超出策略 gap、内容切换或时钟不确定度超限均会关闭/分裂 episode。`GAP_DETECTED → OPEN` 不存在；恢复媒体必须新建 episode，或在持久化 gap 后将 `continuity_start_pts` 推进到 gap 之后，任何 scope 都不得跨越该边界。
- 已通知的 stable scope 出现冲突时只创建 revision；更正是否通知由 `InterruptionPolicy` 决定。

## 音频充分性、缓存恢复与迟到事实

```text
AudioCapabilitySnapshot(NO_AUDIO_TRACK_VERIFIED)
  → SemanticAudioRequirementDecision(AUDIO_NOT_REQUIRED_VERIFIED) | AUDIO_REQUIRED_UNRESOLVED

PC_BUFFER_ONLY → durable fragments/outbox → resume manifest validation
  → CONTIGUOUS → PC_LOCAL_ACTIVE
  → GAP_DETECTED | QUARANTINED → L0 only / new episode

late fact → LateFactAdmission
  → REASSESS_UNPRESENTED | REVISE_PRESENTED | INVALIDATE_WITHDRAW | QUARANTINE
```

- `NO_AUDIO_TRACK_VERIFIED` 只是采集事实；只有同 scope、同 PTS、同 consent/source 的视觉/文字充分证据与 `SemanticAudioRequirementDecision` 才能转换为 `AUDIO_NOT_REQUIRED`。
- resume manifest 必须在当前 consent generation 下核对连续 sequence、PTS、媒体/local-storage hash、ACK cursor 与幂等键。endpoint 一致性不是 lease 授权；T091 的 route resolver 仍是唯一 owner 真源。
- late fact 绝不能推进 watermark、续租 heartbeat 或直接创建 L1。未呈现 scope 只重评，已呈现 scope 走 revision/withdraw，超出 policy lateness、重放、跨 scope 或前代不匹配进入 quarantine。

## L1、投递与通知

```text
LearningMoment: QUALIFYING → ACTIVE_DISCOVER → REVISED | WITHDRAWN | TOMBSTONED

L1_ELIGIBLE (PC)
  = STABLE + non-ambiguous episode + WINDOW_COMPLETE + evidence-sufficiency profile + RuntimeSemanticRisk=CLEAR + INTEREST_CONFIRMED + OFFERABLE + LEARNING_SAFE + valid audio/media + current consent fence
→ create-or-hit stable LearningMoment + immutable LearningMomentRevision
→ PACKAGE_PERSISTED (Android transaction)
→ PC_ACKED
→ DEVICE_DISPATCH_AUTHORIZED | DEFERRED | SUPPRESSED_CONTEXT
DEVICE_DISPATCH_AUTHORIZED → NOTIFY_NOW | SUPPRESSED_CONTEXT
```

`briefId` 是 L1 路由主键；`packageId + packageRevisionId` 是其内容容器和版本。`LearningMoment.interventionKey` 才是普通通知主键，固定为 `l1:learnerId:momentId:NORMAL`；scope hash、package revision 和兴趣重评都不得改变它。一个 moment 的普通通知只能原子领取一次，普通修订只刷新 brief/Discover。媒体 episode 的默认预算是一个普通 slot；第二个 slot 需要不同重大 anchor、学生主动进入或订阅的策略事实，不能由图谱补全或模型重跑取得。

`L1_ELIGIBLE` 还隐含有效 `AudioCapabilitySnapshot`、已认证 `MediaSecuritySession`、`ContentSafetyAssessment=LEARNING_SAFE` 与同一 `learnerId` 的强制授权校验；任一失败只保留 L0/发现页质量状态。

`NOTIFY_NOW` 还要求未过期的 `DeliveryContextSnapshot=SAME_SCOPE | CONTINUOUS_SAME_EPISODE`。连续关系必须同时满足同 learner/episode、PTS 连续、概念 lineage 相关、前台有效和归属可信；它不是“只要仍在前台”的替代。`STALE/UNKNOWN` 走 `DEFERRED` 或 `SUPPRESSED_CONTEXT`，不得以旧 episode/旧 PTS 补发 heads-up。`POSTED/DEFERRED/SUPPRESSED_CONTEXT` 属于 `NotificationAttempt`，绝不能回写或改变 LearningMoment 的存在与版本。

`DEVICE_DISPATCH_AUTHORIZED` 由 Android 生成短时一次性 nonce。Android notification worker 在 claim、post 前和 post 后比较当前 nonce、scope relation、package revision、consent/fence 和本机前台/锁屏可见性；不匹配时消费 nonce、写 `SUPPRESSED_CONTEXT` 并保留 Discover。锁屏默认只投递不含学习内容的最小文本；通知点击不授予 brief 读取权限。

## 正式作答打扰栅栏

`AssessmentSessionState`：

```text
DAILY_INTEREST
  → ASSESSMENT_START_CONFIRMED → FORMAL_ASSESSMENT_FENCE (learner-wide transactional cancel/suppress notification, practice, correction outboxes)
  → ACTIVE
  → SUSPENDED ↔ ACTIVE
  → SUBMISSION_PENDING → SUBMITTED | ENDED_CONFIRMED
  → REVIEW_READY → POST_ASSESSMENT_REVIEW
```

- 模型/画面猜测不能进入 fence；只有学生显式启动或受控任务启动 receipt 能进入。fence 固定绑定 `learnerId + assessmentId + fenceGeneration`，首期作用域为 learner-wide。
- fence 生效前已提交、延后、重试或已 posted 的触达都必须取消/拒绝；深链只可显示“作答中不可介入”。
- Android Back、锁屏、前后台切换、进程死亡、网络断开或未确认离线草稿只能进入 `SUSPENDED/SUBMISSION_PENDING`，fence 保持；它们绝不等于 `ASSESSMENT_SESSION_CLOSED`。
- 只有同一 `assessmentId + learnerId + fenceGeneration` 的学生显式结束或交卷产生幂等且持久化的 `ASSESSMENT_CLOSURE_CONFIRMED` receipt 后，才可到 `SUBMITTED/ENDED_CONFIRMED → REVIEW_READY` 并撤除 fence；另一 task/设备的 close 不能解锁，重复 close 不得重复复盘或恢复旧通知。

## 授权撤回版本栅栏

```text
ACTIVE generation=N → REVOKED generation=N+1 → DELETE_PENDING → DELETE_ACKED | DELETE_ESCALATED
```

- 消息、媒体分片、ACK、缓存恢复、通知和 patch 必须匹配当前 generation；旧 generation 永远拒绝，即使 token/lease 尚未到期。

## 质量与安全事故熔断

```text
CLOSED → OPEN_L0_ONLY | OPEN_ALL_DELIVERY_DISABLED
OPEN_* → RECOVERY_PENDING → CLOSED
```

- 打开 `SafetyCircuitBreaker` 时取消未投递的 L1/L3/L4、通知和导出，已投递内容按修订/撤回策略处理；L0 只保留最小审计和删除所需证据。
- 模型输出、自动重试或同一旧 policy 不能关闭 breaker；只有根因证据、冻结样本重验、新 policy bundle 和人工批准 receipt 齐备才可进入 `RECOVERY_PENDING`。

## ContentGraphRevision

```text
PARENT_KNOWN → APPLIED
PARENT_MISSING → ORPHAN_STAGED → APPLIED | DEAD_LETTER
```

- revision 形成有向无环父链；重复 revision 按哈希幂等。
- `StudentGraphPatch` 是覆盖层。AI 基图更新后，目标仍存在则自动重基；目标删除/冲突则标记 `PATCH_REBASE_REQUIRED`，由学生选择保留、迁移或丢弃。图谱 revision、网页补全或学生 patch 不能重新开放已撤回 moment、重评兴趣或创建普通通知。

## 负反馈与策略

```text
Feedback: ACTIVE → EXPIRED | REVOKED
NotificationAttempt: PENDING → CLAIMED(lease) → POSTING → POSTED
  → OPENED | DEFER_BY_USER | DISMISSED | CANCELLED_REVOKED
DEFERRED → CLAIMED | EXPIRED | SUPPRESSED_CONTEXT
```

系统阻断、用户稍后查看、单次 dismiss、明确“不感兴趣”、主题屏蔽、安静时段是不同事件；只有明确反馈或策略定义的重复模式可抑制同主题后续通知。worker 在领取、post 前和 post 后均检查 `ConsentFence`、`FORMAL_ASSESSMENT_FENCE` 与 lease；`CANCELLED_REVOKED > OPENED > DEFER_BY_USER > DISMISSED`，低优先级回调不可覆盖高优先级事件。

## 观测、弃答与学生控制

```text
Observation: VERIFIED_PLAYER | SCREEN_INFERRED | UNKNOWN
RuntimeRisk: CLEAR → ABSTAIN_L0_ONLY | REQUIRE_REVIEW
DeliveryContext: SAME_SCOPE | CONTINUOUS_SAME_EPISODE → STALE | UNKNOWN
PersonalEvidenceIndex: ACTIVE → REVOKED_BY_STUDENT
```

- 只有 `VERIFIED_PLAYER` 能写精确播放进度；`SCREEN_INFERRED/UNKNOWN` 不得生成或显示精确覆盖、自然结束、倍速、Seek。
- `ABSTAIN_L0_ONLY` 不影响已保存 L0 质量证据，但禁止该 scope 创建或补发 L1；风险恢复后必须创建新 scope/revision 与新 assessment，不能改写旧拒绝。
- 学生撤销个人索引或主题打扰规则后，未来策略立即使用新版本；历史 evidence 仍只读可审计，系统事件不能成为个人索引正向来源。

## 深链访问与学习活动版本

```text
DeepLink → BriefAccessResolver
  → ACTIVE | REVISED | WITHDRAWN | EXPIRED | NOT_FOUND | SCOPE_DENIED | STORAGE_PENDING
```

- 非 `ACTIVE/REVISED` 不加载内容；冷启动 Back 合成到同 scope 的 Discover，不得进入旧样例或退出应用。
- 每个 `LearningActivity` 固定 brief/package/graph/question/validation/submission 版本。修订后旧 activity 只读审计，新动作创建新版本 activity。

## 离线作答对账

```text
L3: DRAFT → LOCALLY_RECORDED_PENDING_RECONCILIATION → FINALIZED | REJECTED_REVOKED
L4: DRAFT → QUEUED → DELIVERED | REJECTED
```

- 离线输入可保存但不显示最终分数、不入长期索引；联网后必须重新核验当前 validation、课程对齐、scope 与 consent fence。

## 删除升级与系统通知撤销

```text
DELETE_PENDING → DELETE_ACKED
DELETE_PENDING → DELETE_FAILED → retry | DELETE_ESCALATED
POSTED notification → CANCELLED_REVOKED
```

- `DELETE_ESCALATED` 不是“删除完成”：应用内治理状态必须显示未确认目标与原因，并阻止任何内容读取或重新投递。
- 一旦 root 被撤回，已 posted 的 L1 系统通知必须取消；即使 OEM 历史展示短暂残留，点击也只能进入“内容已撤回”状态，不能恢复 brief。

## L3 题目校验与撤销

```text
Question: DRAFT (validation=UNVERIFIED)
  → PUBLISHABLE (validation=VERIFIED_BY_RULE | VERIFIED_BY_SOURCE)
  → PUBLISHED
validation=UNVERIFIED | REJECTED | REVOKED → Question=WITHDRAWN
```

- 题目、正确答案、解析和判分规则必须同一 `QuestionValidation` 版本一起发布；生成题目的模型不能成为唯一验证者。
- 权威来源、校验器或依据被撤销时，已发布题目立即 `WITHDRAWN`；历史作答保留原题版本与审计，不按已失效答案生成新的成绩结论。

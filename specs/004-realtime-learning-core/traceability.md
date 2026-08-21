# 需求—实现—验收追溯矩阵

| ID | 冻结需求 | 实现落点 | 必须通过的证据 |
|---|---|---|---|
| R01 | L0 从内容出现开始持续理解 | PC episode/scope/semantic ledger；Android capture transport | 连续真机流的 PTS、语义增量、队列水位日志 |
| R02 | L1=完整窗口语义×真实兴趣 | `SemanticScope`、`InterestAssessment`、`LearningOfferAssessment` | 正/负领域测试与真实 L1 简报 |
| R03 | L1 不等整视频/L2–L4 | `CONTENT_ANALYSIS_PACKAGE.v2.l1`、增量 package | 长视频未结束时的 heads-up 与后续图谱修订 |
| R04 | 音频失败先修复，语义不足不得 L1 | 音频质量状态、scope 稳定门 | 同源音频缺口负向验收；纯视觉例外证据 |
| R05 | 图文读完、直播按语义窗口 | `ANALYSIS_OBSERVED` 行为/边界适配器 | 图文、直播样本的可回放事实与负例 |
| R06 | L1 是系统高优先级消息，所有层在发现页留档 | notification outbox、deep link、Discover Room query | 真机横幅、点击深链、权限关闭时发现页记录 |
| R07 | L2 图谱逐步生长并联网补全 | `ContentGraphRevision`、`KnowledgeEnrichmentAgent` | 有来源的增量 revision、冲突状态与 UI 来源抽屉 |
| R08 | 手工修改 AI 图谱，不污染长期画像 | `StudentGraphPatch`、`PersonalEvidenceIndex` | AI 基图不可篡改、学生 patch 可回放、无自动 profile 写入 |
| R09 | L3 有答案客观题，L4 主观论证 | practice feature、答案校验模型 | 有依据的 L3 判分与 L4 回执 |
| R10 | PC 本地优先；断连只缓存 | `PcLocalModelTransport`、outbox、缓存恢复 | 断网恢复同 episode、无自动云切换 |
| R11 | 无 PC 的云接口不造假 | `CloudAnalysisTransport` availability | 无网关显示 pending；真实网关上线后另做 E2E |
| R12 | 眼镜与手机同一领域链但不得虚称已接入 | `GlassesCaptureSource`、统一 contract | 真实设备媒体、时钟、许可验收；未完成状态明确 |
| R13 | 不做人格/能力/医学诊断 | profile policy、UI copy、数据模型 | 静态审查与负向 UI/导出测试 |
| R14 | 私密/未知来源不外发 | ingress source policy、撤回/删除审计 | 禁止页面、撤回、缓存清理真机/服务端验收 |
| R15 | 不把构建、mock、截图说成闭环 | 阶段 4 验收包 | 同一次真实操作的媒体、推理、通知与点击证据 |
| R16 | 打扰策略可撤销且不误读系统状态 | `InterruptionPolicy`、`InterruptionFeedback`、通知 outbox | 稍后/dismiss/主题屏蔽/系统阻断/撤销的隔离回归 |
| R17 | 云端未授权前绝不出域，上线后可删除可审计 | `CloudDataPolicy`、云 transport、删除 receipt | disabled 网络负例；已启用的 allowlist/保留期/删除回执 |
| R18 | 旧候选与图谱数据迁移可验证、可回退 | `migration.md`、Room 迁移、导出 | 映射计数/hash、quarantine、只读回滚与旧入口删除门 |
| R19 | PC/纸笔教材为独立学习入口 | `PCLearningSession`、来源适配器、工作台 | 不经 Android 兴趣的 session、证据、回执验收 |
| R20 | 本地敏感数据有最小保留与设备撤销 | `RetentionPolicySnapshot`、本地密钥/配对撤销 | 到期清理 receipt、丢失设备撤销和无公共明文落盘审计 |
| R21 | 配对凭据短期、可轮换，停止/解绑能终止运行中链路 | Keystore device credential、token rotation、capture revoke gate | token 重放/过期/撤销、服务重启、活动 worker/lease 终止验收 |
| R22 | 入站内容包原子持久化后才 ACK | Room package transaction、receipt、notification outbox | 注入任一步写入失败后无半包、可重投、无提前 ACK |
| R23 | 捕获范围与私密页策略可执行、不伪造来源识别 | `CapturePolicySnapshot`、v2 capture ingress | single-app/whole-screen/unknown-sentinel 的传输前负例 |
| R24 | 解绑是停止、撤销、结算/删除的可恢复事务 | unpair state machine、capture supervisor、receipt | 解绑中断重试后无 RTSP/worker/lease/投递残留 |
| R25 | 不把屏幕流伪装成播放器 API 或进度事实 | `ObservationCapability`、行为 reducer | 无进度证据时不产生“看完/2/3/倍速/Seek”结论的负例 |
| R26 | 语义质量由外部标注回归证明，非模型自证 | `SemanticQualityPolicy`、回归集、release gate | 版本化质量报告、失败版本 L1 禁止、回归对比 |
| R27 | 学生身份与设备/网络身份分离，跨端不串数据 | `LearnerScope`、scope-bound transport/DB | 共享 PC、换设备、跨 scope ACK/读取/删除/迁移的隔离负例 |
| R28 | 撤回有可见终态，已投递通知和深链不可绕过删除 | `DeletionJob`、notification cancellation、tombstone resolver | 删除 deadline/升级、系统通知取消、深链/缓存负向验收 |
| R29 | 正式作答只记录、交卷后才复盘 | `AssessmentSession`、mode gate、EvidenceCard | 作答中零干预；交卷后按证据生成差异化复盘 |
| R30 | 受控课程资源与证据卡可解释、可版本回放 | `CurriculumResource`、`EVIDENCE_CARD.v2` | 事实/解释/反证分离、资源版本/许可证、review 回归 |
| R31 | 增强状态流只作质量/趋势证据，不作诊断或 L1 触发器 | `StateSignalWindow`、时间/质量 gate | 伪迹/时钟超限退出融合，禁止诊断/单独触达 |
| R32 | 教师/研究复核仅能经可撤回的脱敏导出 | `ControlledEvidenceExport`、scope/field allowlist | 默认拒绝原始媒体/状态流/画像，撤回后链接失效 |
| R33 | 竞赛能力主张必须经版本化指标、消融与等级标记验证 | `CompetitionValidationProfile`、验收报告 | 指标原始日志、对照/错误案例、能力等级审计 |
| R34 | “实时”必须有每种设备—模型配置的批准 SLO 与持续流证明 | `RealtimeServiceLevelPolicy`、runtime benchmark gate | 同配置持续流 p95/max、吞吐、队列、过载原始日志与批准报告 |
| R35 | 同源音频可采集性、来源和同步误差必须可审计 | `AudioCapabilitySnapshot`、audio recovery gate | 受支持/受限应用矩阵、音画同步和关键语音失败负例 |
| R36 | 屏幕/音频媒体 data plane 必须加密、双向认证、防重放 | `MediaSecuritySession`、fragment auth contract | 未认证/过期/重放/跨 scope/明文 endpoint 均被拒绝的负例 |
| R37 | 内容边界歧义不能错误触发兴趣、L1 或图谱合并 | `EpisodeBoundaryResolver`、episode boundary ledger | 分屏/浮窗/广告/切换样本中 `EPISODE_AMBIGUOUS` 隔离回放 |
| R38 | 无 PC 用户只有经真机验收的团队云链才算可用 | `CloudAnalysisTransport`、CloudDataPolicy、cloud gateway | Android 云端授权→L0→L1→撤回删除同次真机闭环 |
| R39 | learner scope 在存储、消息、缓存和授权层强制隔离 | composite DB/FK、scope-bound envelopes/leases | 共享 PC/换机/重放 token 下跨 scope 读写、ACK、深链、删除拒绝 |
| R40 | 联网检索必须在隔离沙箱内，不能受网页指令或内网资源控制 | `retrieval-sandbox.md`、enrichment fetcher | SSRF/DNS 重绑定/重定向/提示注入/超大附件负例与删除回执 |
| R41 | 高风险内容与适用敏感/未成年人授权不产生不当学习介入 | `ContentSafetyAssessment`、consent capability gate | 风险内容仅记录/复核、无 heads-up；缺适用授权时 disabled 的负例 |
| R42 | 正式作答启动必须原子阻断既有和新触达 | `FORMAL_ASSESSMENT_FENCE`、跨端 outbox cancellation | pending/deferred/retry/posted 通知在 mode 切换、进程恢复、断网下均不介入 |
| R43 | 撤回后的在途/重放消息不能重新落库或投递 | `ConsentFence`、generation-aware ingress/outbox | 删除并发、缓存恢复、旧 token/lease、ACK/patch 竞态均拒绝 |
| R44 | 系统行为不能污染兴趣、画像或二次打扰 | `LearningActivityOrigin`、行为 reducer | 点击/恢复/刷新/迁移区分；系统 origin 不参与兴趣或画像 |
| R45 | L3/课程性复盘必须与 learner 当前课程资源适配 | `CurriculumAlignment`、QuestionValidation | 无适配资源时 L3 unavailable；撤销/换学段后不重判旧作答 |
| R46 | 通知投递与撤回必须可线性化，不能被 worker/回调竞态复活 | `NotificationAttempt`、lease/action nonce | notify 前后撤回、重复 PendingIntent、进程恢复下无重复/复活通知 |
| R47 | 学习活动必须固定不可变内容版本，不能被修订重解释 | version-bound `LearningActivity` | L1–L4 历史活动回放使用原 brief/graph/question/validation 版本 |
| R48 | 深链冷启动和不可访问状态不能泄露/回退错误内容 | `BriefAccessResolver`、scope-bound navigation | 撤回/过期/quarantine/Room 未就绪/scope denied 的 UI 与 Back 回归 |
| R49 | 离线 L3/L4 必须待重新核对，不能提前给最终结论 | answer/submission reconciliation state | 离线撤销、恢复对账、最终化/拒绝和长期索引负例 |
| R50 | 通知点击、稍后、删除回调必须有稳定因果优先级 | attempt event reducer | click/delete/action 并发、幂等和策略不污染回归 |
| R51 | 策略必须可验签、可撤销、可兼容并在投递前重评 | `PolicyBundle`、policy verifier | 签名/过期/撤销/不兼容/安全升级下失败关闭与未呈现包重评 |
| R52 | 证据链必须能证明未篡改，链断不能称真实闭环 | `EvidenceIntegrityLedger`、device/service signing | capture→L0→package→操作→receipt 的验签、断链/重放 quarantine |
| R53 | 多设备可并行来源但不能重复采集、重复通知或旧设备控制 | ownership/delivery authority leases | 同源竞争、换机、撤销、离线恢复、authority epoch 的拒绝/唯一投递 |
| R54 | 删除完成必须覆盖备份、聚合、索引、密钥和恢复流程 | `BackupDeletionManifest`、restore fence | 冷备份/DR/索引/密钥撤销、恢复前 tombstone 重放、未完成 escalation |
| R55 | 协议演进不允许字段猜测或降级回旧候选链 | `ProtocolCompatibilityProfile` | 老客户端/老网关/未知能力拒绝，升级提示，无 candidate fallback |
| R56 | 策略验签根必须可轮换、可紧急撤销且不可回退 | `PolicyTrustRoot`、bundle verifier | 未知/旧/撤销根、密钥轮换、紧急撤销和最低版本负例 |
| R57 | 证据链必须能检测备份恢复、换机和离线重放导致的账本回滚 | `LedgerCheckpoint`、secure-store/remote anchor | checkpoint 断裂、DB rollback、旧备份/旧 key 导入 quarantine |
| R58 | 媒体顺序与墙上时间必须分离，时间不可信时保守处理 | `TimeAuthority`、policy time gate | 墙钟回拨/跳变、离线/校准恢复、quiet/delete/token/SLO 时间负例 |
| R59 | 能力档位必须允许真实本地核心渐进交付，禁止全有或全无声明 | `CapabilityProfile`、release gate | UI/本地 L0/L1/云/眼镜/L3L4/竞赛各档位独立通过、降级与报告验证 |
| R60 | L1 证据门应随内容模态而变，且不得伪造第三方播放器进度 | `EvidenceSufficiencyProfile`、`ObservationTier`、behavior adapter | 视频/图文/直播充分性正反例；无 adapter 不生精确进度，adapter 证据可回放 |
| R61 | 运行时未知/冲突窗口必须弃答，静态回归不能替代逐窗口风险门 | `RuntimeSemanticRiskAssessment`、scope reducer | 未知领域/模态冲突/退化仅 L0 或复核，恢复仅生成新 revision |
| R62 | 高优先级通知只在学生仍关注同一内容时发送 | `DeliveryContextSnapshot`、notification outbox | 刷走/锁屏/迟到/nonce 变化时 heads-up 抑制、Discover 保留 |
| R63 | 实时链必须受手机和 PC 资源仲裁，不能隐形积压或消耗失控 | `ResourceGovernorSnapshot`、capture supervisor、SLO reporter | 电量/热/空间/网络/队列过载的降级、暂停、恢复与无丢片验收 |
| R64 | 音频“尽量修复”须以目标组合真机支持矩阵而非抽象状态描述 | `AudioSupportMatrixEntry`、audio recovery | 支持/失配/DRM/应用拒绝的样本、恢复动作与受限 UI |
| R65 | 学生能解释并撤销未来打扰与长期索引，系统行为不构成偏好 | L1 evidence drawer、policy/index reducer | 证据展示、主题/索引撤销、历史审计与系统阻断负例 |
| R66 | 适用敏感、未成年人、云端和导出处理必须有独立、可撤销资格，普通采集授权不可替代 | `ProcessingEligibilityGrant`、capability gate | 缺失/过期/撤销/跨 scope/grant 冒充负例；对应能力 unavailable |
| R67 | v2 切换与回退不能产生双链副作用或复活旧 candidate 通知 | `CutoverReleaseGate`、migration cutover receipt | shadow 无副作用、active 签名门、disabled 回退与 legacy read-only 回归 |
| R68 | 适用处理资格必须持久化、scope/generation 绑定，恢复不能回退到普通采集授权 | `ProcessingEligibilityGrant`、grant resolver | 进程死亡、过期/撤销、跨 scope、普通 consent 冒充均失败关闭 |
| R69 | 正式作答只有明确结束/交卷才可复盘，异常退出不能提前解除零介入 fence | `AssessmentSessionState`、closure receipt | Back/崩溃/锁屏/断网/重复 close/离线交卷的零介入与复盘时序 |
| R70 | 所有学生关键路径必须满足 Android 无障碍可达性，不以视觉截图替代 | Compose Semantics/accessibility baseline | TalkBack、动态字体、焦点、触控、非颜色状态和通知 action 验收 |
| R71 | 通知阻断状态必须可解释、可修复时可进入系统设置且不绕过用户控制 | `NotificationCapabilitySnapshot`、settings refresh | 权限/频道/DND/OEM 阻断、设置返回刷新、Discover 保留回归 |
| R72 | 模型结论和能力主张必须可由完整推理配置复现 | `InferenceProvenance`、output hash | 权重/prompt/预处理/采样/运行时/输入范围缺失拒绝；可重现实验 |
| R73 | 不可信媒体/网页/模型输出不能改变工具或系统权限 | `ModelExecutionCapability`、sandbox | 提示注入、网络/凭据/设备/导出越权全部拒绝，检索仅 L2 |
| R74 | 助手只能建议和经学生逐次确认的允许动作，不能代办第三方操作 | `StudentActionProposal`、action gate | 未确认/过期/跨 scope/第三方/Accessibility/ADB/隐式 Intent 负例 |
| R75 | 质量/竞赛评测必须防止数据泄漏、无许可证和撤回数据使用 | `EvaluationDatasetManifest`、split/leak detector | episode/learner/来源/设备隔离、冻结测试、许可证/撤回回归 |
| R76 | 质量/安全/完整性事故必须可立即熔断介入并受控恢复 | `SafetyCircuitBreaker`、recovery receipt | 停止投递、进程恢复不自闭合、人工恢复/未呈现包重评 |
| R85 | 媒体连续、语义范围、学习触达和通知投递必须分责，避免修订/图谱补全重复打扰 | `LearningMoment`、moment revision、通知 slot reservation | 长视频多主题、scope/package/interest 修订、图谱/patch、权限阻断与 correction 的去重/保留回归 |
| R77 | 实施顺序不得绕过功能硬门，新增任务也须成为 release 前置 | G1–G6 dependency gates、`CapabilityProfile` | 任务乱序、fixture/shadow/debug/回退下生产副作用拒绝与发布报告 |
| R78 | 旧 candidate/visit 链永不产生生产 L1 或系统通知 | legacy read-only adapters、Manifest/inbox/receiver deny | 合法 v1 payload、ADB、fixture/shadow 均零通知/零新内容 |
| R79 | 每个实时 session 必有唯一分析 route，PC 缓存绝不自动/隐式切云 | `AnalysisRouteLease`、route epoch/closure receipt | 断连、grant、恢复、换机、旧缓存出域和双 route 负例 |
| R80 | L0 活跃必须有双时钟心跳，停滞不得冒充实时或产生 L1 | `L0SemanticHeartbeat`、`SEMANTIC_STALLED` | worker 卡死/capture 存活、deadline、恢复与迟到包负例 |
| R81 | L1 当前相关允许同 episode 连续语义，不得因 scope 边界漏触达或重复打扰 | `DeliveryContextSnapshot` relation、episode budget | 同 scope/连续下一 scope/切换/gap/lineage/预算回归 |
| R82 | 正式作答 fence 只能显式建立并由同一 assessment generation 解除 | learner-wide `FormalAssessmentFence`、start/closure receipt | 模型猜测、跨 task/device close、崩溃/断网和幂等 close 负例 |
| R83 | 兴趣只能由同会话、同来源、同许可、连续且可回放的独立行为证据确认 | `BehaviorEvent` attribution/PTS/adapter/attestation、scope-bound `InterestAssessment` | 跨 session/source/consent、UNKNOWN、过期、重放、scope 外、伪进度拒绝；连续下一 scope 正例 |
| R84 | heads-up 必须在 Android 本机二次验证且锁屏默认最小披露 | `deviceDispatchNonce`、notification worker、lockscreen disclosure policy | nonce/context/fence/revision 变化零 heads-up；锁屏脱敏、深链访问拒绝和用户可见性回归 |

任何任务、PR 或验收报告必须引用至少一个 R-ID；没有 R-ID 的实现不进入主链。

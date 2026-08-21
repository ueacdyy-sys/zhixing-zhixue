# 实时学习核心重构任务清单

## Phase 1：契约与领域防线

- [X] T001 [P] [R01,R02] 在 `mobile-edge/scripts/realtime_runtime/` 为 `ContentEpisode`、`SemanticScope`、稳定/修订状态新增失败测试。
- [X] T002 [P] [R02,R05] 为兴趣、学习介入、负反馈和观测方法写纯领域测试；已固定系统 delivery/restore 不得确认兴趣、弱/未知单事件不得单独确认、同 episode/前台/授权 generation 约束、兴趣与 offer 独立、系统/OEM 阻断不写负反馈。
- [X] T003 [P] [R04,R10] 已在 `realtime_runtime/contracts.py` 与 `test_realtime_audio_continuity_contracts.py` 固化：无轨不等于音频非必要、同步时钟/阈值、持久 fragment/ACK/gap resume 与 late admission 的失败关闭；运行时账本/Android outbox/route authority 仍分别由 T004/T014/T091 实施。
- [X] T004 [R01,R02] 已在 `realtime_runtime/semantic_ledger.py` 以 SQLite 实现不可变 `RealtimeSemanticFact`、连续 watermark、scope predecessor/hash/revision 与 presentation-anchored late admission；旧 candidate ledger 保持只读，T007 才允许显式接入 v2 L0。
- [X] T005 [R02,R06] 已在 `realtime_runtime/content_package.py` 固化 `CONTENT_ANALYSIS_PACKAGE.v2.l1` 的唯一 L1 schema、嵌入 `L1LearningBrief` 与 `PackagePersistenceReceipt` 契约；candidate/visit/window、scope/兴趣/offer/route/音频/风险/证据/修订不符均失败关闭。Android 事务入站和 PC outbox 由 T006/T015 实施。
- [X] T006 [R06] 已在 `realtime_runtime/package_outbox.py` 实现 PC package revision/payload/message 幂等、delivery lease 与 scope-bound `PackagePersistenceReceipt` ACK；通知状态不参与 ACK。Android Room 事务与实际 receipt 发送由 T015 实施。

## Phase 2：PC 实时分析与内容图谱

- [ ] T007 [R01,R04] 将 `realtime_fragment_worker.py`、`pipeline.py` 的输出从 `FusedCandidate` 改接 L0 事实/scope，不取消已封存片段。已加入只读 `legacy_l0_adapter`：仅将带 lane artifact hash 的 `CANDIDATE_ONLY` 投影为 L0 evidence fact；runner 已具备同 session/learner/consent generation/epoch 的 route 配置解析，但在 T051 加密媒体、双向认证、分片 MAC 与 anti-replay 未实现前明确拒绝启用 v2 L0 投影。仍缺 v2 scope reducer，故不得标完成或生成 L1。
- [ ] T008 [R02,R03] 在 PC gateway 实现行为事件入站、兴趣评估、LearningOfferAssessment 和实时 L1 简报投递。
- [ ] T009 [R07] 实现低优先级 `KnowledgeEnrichmentAgent` 与 `CONTENT_GRAPH_REVISION.v2`；来源/冲突/预算/取消必须可审计。
- [ ] T010 [R07,R08] 在 PC 侧区分 content graph revision、student patch、personal evidence index，切断自动 profile 写入。
- [ ] T011 [R10,R11] 保留 PC local transport；定义云端同构 contract 与 unavailable 状态，不配置真实云即不执行分析。

## Phase 3：Android 数据、传输与通知

- [ ] T012 [P] [R01,R02] 在 `learning-domain` 新建 Kotlin episode/scope/assessment/revision reducer 及先失败测试。
- [ ] T013 [P] [R06,R08,R16] 引入 Room schema、迁移和 DAO：brief、package、content graph、student patch、personal index、notification outbox、打扰反馈/策略与题目校验记录。
- [ ] T014 [R10,R11] 实现 `AnalysisTransport`、PC v2 TLS 适配、缓存续传和 Cloud unavailable UI state。
- [ ] T015 [R06] 改造 `PcDeliveryClient`/inbox：Room 原子持久化后 ACK；通知状态独立出站箱。
- [ ] T016 [R06] 改造 `AndroidStudentNotice` 与深链为 `briefId`，实现能力检测、去重、抑制、修订更正与真机日志。
- [ ] T017 [R08,R18] 按 `migration.md` 迁移旧图谱编辑事件，支持 AI 基图上的 rename/note/edge/hide/correct patch，并生成计数/hash/quarantine 报告。

## Phase 4：V5 行为重构

- [ ] T018 [P] [R06] 将 V5 token/组件抽至 design system；保持既有字体、信息架构与连接页唯一媒体入口。
- [ ] T019 [R06] 引入 Navigation Compose、`l1/{briefId}` 深链、ViewModel/StateFlow 和系统 Back 恢复。
- [ ] T020 [R01,R06] 实现 Discover/L1 的真实 Room Flow；移除 QA 内容作为生产数据源。
- [ ] T021 [R07,R08] L2 只渲染 `ContentGraphRevision + StudentGraphPatch`，无图时呈现真实生成状态；硬编码 canvas 留 debug。
- [ ] T022 [R09] 实现 L3 题干/选项/答案/解析/判分规则、非同生成器的校验记录、失效下架与历史答题审计，以及 L4 回执；未验证内容不可进入对应页面。
- [ ] T023 [R12,R13] 加入眼镜 source adapter 占位/不可用反馈、长期索引展示和诊断禁用审查。

## Phase 5：隐私、迁移与真实验收

- [ ] T024 [R14,R17] 实现传输前来源许可门、未知/禁止页面失败关闭、撤回删除和审计链；CloudDataPolicy 未启用时增加网络零出域负例。
- [ ] T025 [R10] 验收 PC 断连、缓存空间水位、恢复与不切云行为。
- [ ] T026 [R15] 以真实手机媒体完成视频、图文、直播、音频失败、负反馈和迟到结果的验收包。
- [ ] T027 [R06] 在目标 Android/OEM 上验收 heads-up 可见、点击正确、权限关闭/频道关闭降级。
- [ ] T028 [R07,R08] 验收联网图谱增量、来源抽屉、冲突保留、学生修订和长期索引隔离。
- [ ] T029 [R12] 在真实眼镜设备完成媒体/时钟/许可验收；未通过前保持未接入声明。
- [ ] T030 [R15,R18] v2 等价迁移与真实回归通过后，删除 candidate/visit 通知运行入口与旧 JSON 写入。
- [ ] T031 [R16] 实现 `InterruptionPolicy`：时区、安静时段、频率/主题预算、`DEFERRED` 到期、二次提醒、更正提醒和负反馈撤销；系统阻断不得写成负反馈。
- [ ] T032 [R17] 仅在云 policy 冻结、团队网关可用时实施 Cloud transport；验证 allowlist、短期认证、区域/保留期、配额、删除 receipt 与真机端到端链。
- [ ] T033 [R19] 实现 PC 自主学习、纸笔/教材最小来源适配器与独立 session/证据/回执；不得借用手机兴趣链。
- [ ] T034 [R20] 实现本地私有存储/Keystore 密钥、RetentionPolicySnapshot、到期清理 receipt 与配对设备撤销；覆盖公共目录零落盘和失效 lease 负例。
- [ ] T035 [R21] 替换旧 SharedPreferences bearer：已新增独立 v2 P-256 AndroidKeyStore 凭据、PC 公钥登记、15 分钟短 access token、签名+nonce 刷新/轮换与即时 token 撤销；Android 仅保存可信 endpoint/SPKI/设备 ID，token 仅在内存。PC 的 v2 撤销现会同步废弃未完成 delivery lease/outbox，并向该设备所有 `RUNNING/STARTING/RECOVERING` capture worker 写入有序停止信号；已封存证据不删除。现有 capture/control 路仍在旧 bearer，Android 尚未把 v2 client 接到实际会话，且当前网关没有独立、可取消的 enrichment job executor；故不得标完成或把 v2 凭据当作媒体授权。
- [ ] T036 [R21] 为用户“停止同步/采集”建立持久状态；验证 START_STICKY、进程恢复和 DHCP 重连不能在用户停止/解绑/撤回后恢复媒体或投递。
- [ ] T037 [R22] 用单一 Room 事务替换 `AndroidPcResultInbox` 的双存储写入；按 packageRevisionId 去重，事务成功后再 ACK，并为中断/重投/删除写失败测试。
- [ ] T038 [R23] 在 MediaProjection 前冻结 `CapturePolicySnapshot`：记录 system-share scope、目的地和过滤版本；实现未知/敏感画面传输前失败关闭，禁止从像素流虚构 app/video ID。
- [ ] T039 [R24] 把“解除 PC”改为可恢复状态机：先停止本机 capture，再停/撤销 PC session 与 leases，按保留/删除策略收据化清理，最后删除设备凭据；验证任一步中断后可安全重试。
- [ ] T040 [R25] 实现 `ObservationCapability` 与行为 reducer：仅用可复核播放器/内容证据产生进度、自然结束、倍速/Seek 与图文读完事实；未知或弱线索不得伪造覆盖比例或单独开放 L1。
- [ ] T041 [R26] 建立带许可证/脱敏边界的标注回归集、`SemanticQualityPolicy` 与发布门；覆盖事实支持、ASR/OCR 关键遗漏、scope 边界、L1 误触达/漏触达和模型/提示/检索版本失效重测。
- [ ] T042 [R27] 实现 `LearnerScope` 与 scope-bound 主键/DAO/transport/删除；本地 scope 不自动合并，云端必须认证绑定；迁移中无法归属的数据 quarantine。
- [ ] T043 [R28] 实现删除 deadline/receipt/escalation、Android 系统通知取消和撤回深链/缓存拒绝；未确认 target 在治理页可见且不允许重新投递。
- [ ] T044 [R17] 在 Android/PC 类型与网络边界隔离既有直连聊天 API 和 `CloudAnalysisTransport`；为聊天输入建立显式 scope，拒绝任何 capture/episode/graph/profile 自动传入或断连接管。
- [ ] T045 [R29,R30] 实现 `AssessmentSession`、`CurriculumResource`、`EVIDENCE_CARD.v2` 与正式作答 mode gate：作答中服务端/Android 双重拒绝干预，结束后再生成可复核的题目复盘卡。
- [ ] T046 [R31] 定义眼镜、EEG、手表 `StateSignalWindow` 适配契约、质量/伪迹/时钟门与融合退出规则；首期未接入时只显示不可用，禁止诊断与单流触发 L1。
- [ ] T047 [R32] 实现 `ControlledEvidenceExport`：scope/字段/接收方/用途/到期/撤回审计，默认拒绝原始媒体、状态流、聊天和完整画像。
- [ ] T048 [R33] 建立 `CompetitionValidationProfile` 的数据集、标注手册、对照/消融、错误案例和能力声明审计；所有演示/报告按 `IMPLEMENTED_VERIFIED` 等级输出，未测能力不得升级。
- [X] T049 [R34] 在 `mobile-edge/scripts/realtime_runtime/` 先写每个设备—模型 `RealtimeServiceLevelPolicy` 的失败测试，再实现持续输入、p95/max、吞吐、队列、样本量、批准报告与 `NOT_REALTIME` 失败关闭。
- [ ] T050 [R35] 在 `mobile-edge/scripts/realtime_runtime/` 和 Android capture 模块先写 `AudioCapabilitySnapshot` 契约测试，再记录播放/麦克风/混音来源、应用限制、DRM/系统拒绝、同步误差和恢复状态；关键语义受限时禁止 L1。
- [ ] T051 [R36] 在 `mobile-edge` 媒体 ingress/Android transport 为 `MediaSecuritySession` 先写明文、重放、MAC、过期、跨 scope 和 endpoint 枚举负例，再实现加密、双向认证、分片完整性与 anti-replay。
- [ ] T052 [R37] 在 `mobile-edge/scripts/realtime_runtime/` 先写分屏、浮窗、广告、评论区、内容切换和 PTS epoch 重置测试，再实现 `EpisodeBoundaryResolver`、边界账本与 `EPISODE_AMBIGUOUS` 的 L1/图谱/画像失败关闭。
- [ ] T053 [R39] 在 `learning-domain`、Room DAO、PC gateway 与 evidence resolver 先写跨 learner 读写/ACK/deep link/cache/delete 拒绝测试，再实施 `learnerId` 复合主键/FK、envelope 授权和显式 `ScopeTransfer` receipt。
- [ ] T054 [R40] 在 PC `KnowledgeEnrichmentAgent` 的 fetcher 先写私网/metadata、DNS 重绑定、重定向、Cookie、提示注入、压缩炸弹和超时负例，再实现无凭据检索沙箱、来源 allowlist、资源限额与撤回删除。
- [ ] T055 [R41] 在领域/Android/PC 双端先写风险内容、缺适用授权和系统阻断的负例，再实现 `ContentSafetyAssessment`、安全解释/纠错入口、授权主体 capability gate 和 heads-up 拒绝。
- [ ] T056 [R38] 在独立团队云网关与 Android `CloudAnalysisTransport` 先写同构消息、allowlist、配额、认证、删除 receipt 的失败测试，再部署并真机验收无 PC 的授权→L0→L1→撤回删除完整链；未通过不得发布为无 PC 可用。
- [ ] T057 [R34,R35,R36,R37,R38,R39,R40,R41] 以真实媒体、共享 PC、无 PC 云端和恶意检索样本生成同次验收包；将 SLO、音频、加密、边界、scope、安全、撤回和降级原始证据写入 `CompetitionValidationProfile`，任何未过项保持 `UNAVAILABLE/NOT_REALTIME`。
- [ ] T058 [R42] 在 Android/PC/云 outbox 先写正式作答切换、进程恢复、离线和已 posted 通知负例，再实现 `FORMAL_ASSESSMENT_FENCE` 的原子取消/抑制与只读深链。
- [ ] T059 [R43] 在所有 v2 ingress、Room/PC/cloud transaction、ACK、lease、cache resume、patch 和 notification worker 先写撤回竞态失败测试，再实现单调 `ConsentFence`/generation 比对与无副作用拒绝审计。
- [ ] T060 [R44,R47] 在 `learning-domain`、Room 和交互回执先写 system activity、内容修订、撤回和迁移回放测试，再实现 origin 与 brief/package/graph/question/validation/submission 不可变版本绑定。
- [ ] T061 [R45,R49] 在 practice/review domain 先写课程不适配、资源撤销、离线答题/L4、恢复对账和长期索引负例，再实现 `CurriculumAlignment`、L3/L4 reconciliation/delivery 状态与最终化门。
- [ ] T062 [R46,R48,R50] 在 `AndroidStudentNotice`、Navigation Compose 和 notification receiver 先写 worker crash、撤回并发、重复 PendingIntent、click/delete/snooze、深链冷启动/Room 未就绪/scope denied 回归，再实现 `NotificationAttempt` lease/nonce/优先级与 `BriefAccessResolver`/Discover Back 栈。
- [ ] T063 [R51,R55] 在 Android、PC gateway 和未来云 transport 先写签名失效、过期、撤销、回滚、不兼容 schema/能力和策略升级重评负例，再实现 `PolicyBundle` verifier、`ProtocolCompatibilityProfile`、bundle-hash envelope 与失败关闭。
- [ ] T064 [R52] 在媒体 ledger、PC gateway、Room receipt、导出和删除路径先写篡改、断链、重放、旧 key 和无法复现版本负例，再实现签名 `EvidenceIntegrityLedger` 与 verification/quarantine gate。
- [ ] T065 [R53] 在 pairing/capture supervisor/notification outbox 先写同源多设备竞争、authority 切换、撤销、离线恢复和旧 epoch 投递负例，再实现 `CaptureOwnershipLease`、`LearnerDeliveryAuthority` 与唯一通知投递。
- [ ] T066 [R54] 在 Android/PC/云数据生命周期和灾备恢复工具先写备份/索引/聚合/密钥遗漏、恢复泄露和删除未完成负例，再实现 `BackupDeletionManifest`、per-session key revocation、restore tombstone fence 与 escalation receipt。
- [ ] T067 [R55] 在 v2 message codecs、Android/PC/cloud handshake 和旧 candidate adapters 先写 protocol downgrade/未知字段组合负例，再强制仅允许 `ProtocolCompatibilityProfile` 的升级/不可用路径。
- [ ] T068 [R56] 在 Android/PC/cloud 的 policy verifier 与更新路径先写未知根、旧 epoch、撤销根、紧急撤销、根轮换和最低版本负例，再实现 `PolicyTrustRoot`、签名链/撤销列表、受控过渡与不可回退更新。
- [ ] T069 [R57] 在媒体 ledger、Room、PC gateway、备份/换机和云 receipt 路径先写 DB rollback、旧备份、离线重放、key 轮换和锚点缺失负例，再实现不可回退 `LedgerCheckpoint`、安全存储/跨端锚定和 quarantine。
- [ ] T070 [R58] 在 Android/PC/cloud 时间与 retention/notification/token/SLO 路径先写墙钟回拨、跳变、离线、校准恢复和 PTS 正常负例，再实现 `TimeAuthority`、单调顺序、可信时间锚点及不打扰/不误删降级。
- [ ] T071 [R59] 在 `learning-domain`、Room、V5 ViewModel、设置页和验收报告先写本地 UI/L0/L1、云、眼镜、正式学习、竞赛档位升级/降级及 fixture/candidate 负例，再实现 `CapabilityProfile` reducer、真实 unavailable UI 和能力等级投影。
- [ ] T072 [R60] 在 PC domain、Android 行为 reducer 和 V5 证据页面先写视频/图文/直播、纯视觉、无播放器 API、伪造进度与可验证 adapter 的失败测试，再实现 `EvidenceSufficiencyProfile`、`ObservationTier` 与可回放进度证据契约。
- [ ] T073 [R61] 在 L0 scope reducer、质量门和内容包生成器先写未知领域、ASR/OCR/VLM 冲突、关键覆盖不足、运行时退化和恢复 revision 负例，再实现 `RuntimeSemanticRiskAssessment` 与 `ABSTAIN_L0_ONLY` 门。
- [ ] T074 [R62] 在 Android 前台状态、PC package outbox、`AndroidStudentNotice` 和 Room 通知事务先写刷走内容、锁屏/切前台、迟到包、context nonce 变化与过期 snapshot 回归，再实现 `DeliveryContextSnapshot` 和 heads-up 抑制。
- [ ] T075 [R63] 在手机 capture supervisor、PC runtime queue、SLO reporter 和连接页先写低电量、热、低存储、差网络、推理过载、恢复与无声丢片负例，再实现 `ResourceGovernorSnapshot` 与显式降级/暂停状态机。
- [ ] T076 [R64] 建立目标设备—Android—内容应用音频支持测试矩阵；先写能力失配、DRM/应用拒绝、音画失配、恢复重试和失效组合测试，再实现 `AudioSupportMatrixEntry`、恢复决策与真实受限 UI。
- [ ] T077 [R65] 在 L1 详情、设置、长期知识全览和策略 reducer 先写证据来源展示、撤销个人索引、主题/稍后/不感兴趣、系统阻断与历史审计回归，再实现学生可解释与可撤销控制路径。
- [ ] T078 [R66] 在 Android/PC/cloud ingress、任务恢复、通知/outbox 与受控导出先写缺失、过期、撤销、跨 scope 和普通 capture consent 冒充适用授权的负例，再实现 `ProcessingEligibilityGrant`、最小资格 gate 与 capability unavailable 状态。
- [ ] T079 [R67] 在 migration runner、PC/Android transport、通知 outbox 和 capability release gate 先写影子重复采集、影子 L1/画像副作用、v2 启用、故障回退和旧 candidate 复活负例，再实现 `CutoverReleaseGate`、v2 shadow/active/disabled receipt 与旧链只读切换。
- [ ] T080 [R68] 在 Room/DAO、Android/PC/cloud ingress、任务恢复、通知和导出先写 grant 未持久化、进程死亡、过期/撤销恢复、普通 consent 冒充和跨 scope 重放负例，再实现 `processing_eligibility_grants`、统一 grant resolver 与 generation 约束。
- [ ] T081 [R69] 在 assessment domain、Android Back/进程恢复、PC outbox 和 review feature 先写暂停、锁屏、崩溃、断网、重复 close、离线交卷与显式结束回归，再实现 `AssessmentSessionState`、closure receipt 和 fence 解除门。
- [ ] T082 [R70] 在 V5 Compose 页面与 Android 通知 action 先写 Semantics、TalkBack、动态字体、最小触控目标、焦点顺序和非颜色状态的 UI 自动化/真机验收，再实现无障碍基线与回归门。
- [ ] T083 [R71] 在 Android 通知 capability provider、设置页、连接页和 notification worker 先写权限拒绝、频道降级、DND/OEM 阻断、设置跳转/返回刷新、恢复与 Discover 保留回归，再实现 `NotificationCapabilitySnapshot` 与可修复路径。
- [ ] T084 [R72] 在 PC inference runtime、v2 codecs、Room 和竞赛导出先写 prompt/权重/预处理/采样/运行时/输入范围缺失或不匹配负例，再实现 `InferenceProvenance`、输出 hash 和不可复现拒绝门。
- [ ] T085 [R73] 在媒体 worker、检索 agent、工具注册与网络层先写屏幕/语音/网页提示注入、网络/凭据/设备/导出越权负例，再实现 `ModelExecutionCapability` 最小授权与副作用隔离。
- [ ] T086 [R74] 在智能体 UI、intent/工具层、Android service 与审计 reducer 先写未确认、过期、跨 scope、拒绝、第三方 App、Accessibility/ADB/隐式 Intent 绕过负例，再实现 `StudentActionProposal` 和逐次确认门。
- [ ] T087 [R75] 建立 `EvaluationDatasetManifest`、许可证/脱敏、episode/learner/device split、冻结测试集与泄漏检测；先写数据撤回、跨集合重复、同源样本、调参触达测试集和无许可证负例。
- [ ] T088 [R76] 在 L1/L3/L4/outbox/export/release gate 先写质量事故、错误触达、安全/完整性事件、进程恢复和模型自恢复负例，再实现 `SafetyCircuitBreaker`、取消/最小审计、人工恢复 receipt 与未呈现包重评。
- [ ] T089 [R77] 在 release/capability reducer、PC/Android/cloud feature wiring 与迁移入口先写 G1–G6 未完成、任务乱序、shadow、调试开关和回退绕过负例，再实现依赖门检查、`CapabilityProfile` 联动与拒绝性发布报告。
- [X] T090 [R78] 先写旧 Candidate 链即使输入合法也不得授予 L1、Android Manifest 不得导出 Candidate receiver 的失败测试；已将 dispatcher 固定为只读、移除 broadcast receiver entry，保留 codec 仅供迁移。
- [ ] T091 [R79] 在 Android/PC/cloud session router、缓存 resume 和 ingress 先写 PC 断连、云 grant 到达、解绑/恢复、旧缓存出域与双端竞争负例，再实现 `AnalysisRouteLease`、route epoch、关闭 receipt 和仅新 session 的显式云切换。
- [ ] T092 [R80] 在 PC L0 ledger、Android connection state 和 V5 状态投影先写 worker 卡死、ACK watermark 超时、capture 仍存活、连续恢复与旧积压负例，再实现 `L0SemanticHeartbeat`、`SEMANTIC_STALLED` 与 L1 禁止门。已在 v2 SQLite 账本落入 last-ACK-fact、媒体/语义双 watermark 与单调 deadline；仍缺 PC worker 实写、Android 状态投影和 L1/package 门，故不得标完成。
- [ ] T093 [R81] 在 context reducer、PC package outbox、Android notification worker 先写同 scope、同 episode 连续下一窗口、切换 episode、PTS/lineage 断裂、过期和重复 scope 的回归，再实现 `SAME_SCOPE/CONTINUOUS_SAME_EPISODE` 与每 episode 单次通知预算。
- [ ] T094 [R82] 在 assessment domain、Android/PC/cloud outbox 和多设备回执路径先写模型猜测启动、另一 task/设备 close、Back/崩溃/断网与同 assessment 幂等 close 负例，再实现 learner-wide `FormalAssessmentFence`、`ASSESSMENT_START_CONFIRMED` 和 generation-bound closure receipt。
- [X] T095 [R83] 在 Python 领域契约先写并实现 BehaviorEvent 的 session/source/consent、归属状态、PTS/单调到期、adapter/attestation 或 replayable analysis observation、独立性与 target-scope/lineage 约束；连续下一 scope 保持可用，不以同 scope 死锁，单条弱分析观测不得单独确认兴趣。
- [ ] T096 [R84] 在 Android notification outbox/worker、Room 与真机锁屏路径先写 PC snapshot 过期、nonce 重放、context/fence/package revision 变化和锁屏泄露负例，再实现一次性 `deviceDispatchNonce`、本机二次校验、`MINIMAL` 锁屏 payload 与 resolver 回归。
- [ ] T097 [R83] 在 Android 行为适配器、PC ingress、scope ledger 与 adapter registry 先写伪造/未注册 adapter、无效 attestation/foreground snapshot、跨 PTS 域、scope lineage 伪造、gap 后连续关系和 profile 伪造负例；再实现可回放 attestation 验证、scope/lineage 解析与已验签 policy decision trace。
- [X] T098 [R85] 在 Python 领域契约先写并实现 `LearningMoment + LearningMomentRevision`：媒体 episode、scope、图谱 revision 与通知 attempt 分责；稳定 moment key 不含 scope hash/package revision/interest assessment；并覆盖分析观测的独立性与单条弱信号拒绝。Android/PC 持久化、预算 reservation 和 graph/notification 接线仍由后续 T099 实施。
- [ ] T099 [R85] PC portion now has SQLite `LearningMomentLedger`: create-or-hit、revision DAG、package enqueue 前 durable registration、每 episode 第一/第二普通 slot reservation 与已展示 brief 的一次性 correction slot；仍须在 Android Room、notification outbox 与 graph reducer 写长视频多主题、scope/包/兴趣修订、图谱补全、student patch、权限/OEM 阻断、多设备竞争和 correction 通知负例，并完成跨端原子接线后才能标完成。

## 依赖与停止规则

具体阻塞关系以 `capability-profiles.md` 为准：`DOMAIN_UI_INTEGRATION` 完成前不得让 V5 消费新生产数据；`LOCAL_PC_L1` 完成前不得投递真实 L1；T099 完成前不得把 scope/package/图谱修订直接映射为新的普通 heads-up。云、眼镜、正式学习、导出和竞赛按各自档位门控。未部署云网关、未接入眼镜或未实现纸笔/教材适配时，只能完成其 unavailable/未接入负例，不能伪称全系统闭环；面向无 PC 用户发布前 T056 必须通过。每个任务须附 R-ID、测试/日志和失败时的真实降级状态。

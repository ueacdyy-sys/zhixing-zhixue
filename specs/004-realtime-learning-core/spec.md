# 实时学习理解与分级承接（冻结规格）

**状态**：冻结，实施前置规格
**优先级**：P0
**权威顺序**：本文件记录的用户最终口径 > `大赛可行性方案.docx` 与项目汇报 PPT > 旧版候选卡/visit 规格与实现。

## 1. 产品结论

知行智学不是“检测一张屏幕截图后推荐学习卡”的应用。它是以学生已授权的连续内容流为输入，在本地 PC 或未来云端完成持续语义理解，并将语义结果与学生真实行为结合，低打扰地把兴趣转成可主动进入的学习路径的多设备系统。

手机屏幕流与眼镜第一视角流是两条独立的实时理解主链。PC 也是独立学习终端，不是手机链路的下游。

手机屏幕采集具有两种学生在启动时明确选择的持续会话模式，均不按单条视频重复授权：

1. `FULL_CONTINUOUS`：学生一次授权后，前台服务持续向已配对 PC 提供当前屏幕的连续视频流；视频、平台或页面切换只产生新的 `ContentEpisode`，不结束 `CaptureSession`。
2. `SELECTED_APPS`：学生配置允许采集的平台包名。设备端持续维持已授权会话，但仅在允许平台处于前台时向 PC 输出/保存媒体；离开该平台只阻断媒体输出并写入审计，不停止会话，也不要求再次授权。前台平台优先由经授权的 Android 能力观察；平台 API/MCP 是可选增强而非前提，无法取得时可使用设备本地 UI 识别并标注能力与不确定度。

Android 前台服务被学生清理、系统停止或 PC 观察到来源断流时，事件为 `CaptureInterrupted`：已封存片段和已持久化学习记录保留，当前未封存窗口标记 `INTERRUPTED_INCOMPLETE`。它不是删除，也不得伪称学生主动停止；PC 只能如实记录其观察到的断流原因。

## 2. 冻结的 L0–L4 语义

| 层级 | 定义 | 触发与呈现 | 不允许发生的事 |
|---|---|---|---|
| L0 | 对已授权连续内容进行实时端到端理解；持续产出可追溯的画面、语音、文字、动作/内容事实与质量状态 | 从内容出现即开始；应用内“发现”保留记录，但不打扰 | 不能因单帧、OCR、片段完成或观看时长直接生成知识结论或系统通知 |
| L1 | 对当前已形成**稳定语义闭合**的内容窗口，结合停留、覆盖、回看、暂停、自然播放结束等行为证据后生成的轻量学习简报 | Android 高优先级 heads-up 通知；点击默认打开 L1：概念来源、名词解释、当前内容精析、已知关系预览 | 不能只凭单帧、OCR、候选、时长或未解析的音频缺口开放；不能等待整个视频、整张图谱、L3/L4 都完成才创建 |
| L2 | 围绕已进入 L1 内容逐步生长的知识图谱探索 | 学生主动从 L1 进入；图谱由 L1 概念锚点、L0 后续事实和联网检索增量补全 | 不能把自动生成图谱直接写成已掌握或长期画像结论 |
| L3 | 有答案、可核对的客观题训练 | 学生主动进入 | 不能把仅展示文本或例题讲解称为 L3 完成 |
| L4 | 主观题论证、表达或开放任务 | 学生主动进入并提交过程/结果 | 不用一次作答给学生作能力、人格、医学或确定性专注诊断 |

L0–L4 不是按观看时间、通知次数或模型置信度自动升级的计时器。观看覆盖、自然结束、回看等仅是 L1 兴趣判定的证据；它们不能单独构成 L1。

## 3. 内容与兴趣的判定规则

### 3.1 内容类型

- 视频：从出现开始生成 L0 增量语义。自然播放结束、倍速观看的有效覆盖、持续停留和回看均可成为兴趣证据。约 90 秒连续有效观看、约 2/3 覆盖（最低可采信范围 1/2）是当前兴趣策略可使用的不同强度事实；阈值必须由版本化策略配置，不得散落硬编码，更不能替代语义与学习价值判断。
- 图文：必须完成页面主要内容阅读和语义闭合才可进入 L1。页面打开或孤立停留不等于读完。
- 直播：使用连续语义窗口。纯带货、无可验证知识价值的直播保持 L0 记录，不生成知识结论；只有对营销话术、传播机制等具有明确可解释对象的内容才可生成相应分析。
- 静音/音频异常：播放内容应优先修复同源音频采集与对齐。若内容存在未解析的关键语音，状态为 `AUDIO_REQUIRED_UNRESOLVED`，只保留 L0；若系统已证实该窗口无语音信息或视觉/文本证据足以完整覆盖语义，可标记 `AUDIO_NOT_REQUIRED` 并继续按完整语义门判断。音频采集失败本身不得被伪装成“无声内容”。

### 3.2 L1 开放门

PC 端的 `L1_ELIGIBLE` 必须同时具备：

1. 当前内容的一个连续语义窗口已达到 `WINDOW_COMPLETE`，并引用连续媒体/文字证据范围；不要求 episode 或视频已结束；
2. 该窗口具备可学习的解释对象（概念、事件、观点、方法或可证据支撑的营销/传播机制之一），且能生成带证据引用的 `L1LearningBrief`；
3. 兴趣评估引用真实行为事实，并由版本化策略评估为 `INTEREST_CONFIRMED`；
4. `LearningOfferAssessment=OFFERABLE`；
5. 会话许可快照及其 `consentGeneration` 仍有效；
6. `ContentSafetyAssessment=LEARNING_SAFE`，且 episode 边界、learner scope、音频来源与媒体安全状态均已通过本版本策略。

Android 端的 `L1_DELIVERED` 仅在 L1 简报、证据引用和发现页记录同一事务持久化后成立，随后 ACK PC；系统通知是独立的 `L1_NOTIFICATION_ATTEMPTED` 状态。自然播放结束是强正向兴趣证据；倍速播放应按媒体覆盖而非墙上时间计算。正常会话关闭、`CaptureInterrupted` 或 PC 延迟不得使已经成立的 L1 自动失效，也不得删除已封存证据；只有学生明确的 `DeleteRequested` 才触发历史内容级联删除。通知权限不是 L1 资格门：未授予权限时仍写入发现页，只有 heads-up 这一投递渠道不可用。

`WINDOW_COMPLETE` 不是模型返回一句摘要即可成立。它必须有连续 PTS 覆盖、媒体/文字完整性、所需模态质量、范围哈希、语义修订号、事件时间水位与已通过的 `SemanticQualityPolicy` 版本；任一关键缺口、边界改变或后到事实冲突时，scope 进入 `REVISED` 或 `INVALIDATED`，L1 页面展示修订说明并保留旧证据版本。若错误已实质影响学生看到的解释，`InterruptionPolicy` 必须支持一次“更正提醒”，不能静默改写历史。

`SemanticQualityPolicy` 必须按输入类型、模型/提示词版本与设备配置维护独立标注回归集和可审计指标：事实证据支持率、关键语音/文字遗漏、scope 边界正确性、概念解释可追溯性、L1 误触达/漏触达与更正率。模型自报置信度不是质量证明；新模型、提示词、OCR/ASR/VLM 版本、检索策略或阈值变更均须在相同样本上回归。未达到该版本质量门的结果只能保留 L0 质量/失败记录，不得形成 L1。

行为事实必须标明观测来源。`ANDROID_OBSERVED` 只能描述授权、前后台、`SELECTED_APPS` 的允许平台进入/离开和采集连续性；`ANALYSIS_OBSERVED` 只能从同一媒体流中形成带依据的内容边界、语义窗口和有限行为线索。系统不得假称 Android 获得了第三方应用的视频 ID、总时长、倍速、播放进度、Seek 或自然结束事件。若平台提供经学生授权的正式 API/MCP adapter，其能力、视频标识、字段来源和版本必须单独记录；不得把 API 不存在时的 UI 估计写成平台事实。

“自然结束”“覆盖 2/3”“倍速有效覆盖”只能在 PC 从可核验证据（例如可读的同一播放器进度/结束画面、连续 PTS 与内容连续性）生成 `DIRECT_PROGRESS_OBSERVED` 时使用；视觉估计、屏幕静止、MediaProjection 存活、疑似播放器 UI 或单次暂停只能标为 `WEAK_ATTENTION_SIGNAL`，不能记为覆盖比例、自然结束或单独确认兴趣。总时长、进度或内容身份未知时，L1 仍可由**稳定语义窗口 + 其他真实兴趣证据**产生，但界面和审计不得显示“已看 2/3”“已看完”或虚构平台视频 ID。

兴趣策略只能消费已归属同一 episode、归属置信度合格、发生时仍授权且前台有效的事实；每个行为事实必须附 `ObservationCapability`、依据范围和置信等级。没有可用观测能力时按 `UNKNOWN` 处理，不以推测补齐。图文“读完”同样要求主要内容范围、滚动/页面连续性和语义闭合证据，不能由停留时间替代。

行为事实不是客户端可自由填写的“学生明确行为”标签。任何可进入 `INTEREST_CONFIRMED` 的 `BehaviorEvent` 必须以 `learnerId + sessionId + sourceKind + captureConsentId + consentGeneration` 绑定已解析 episode，并记录 `EpisodeAttributionState=RESOLVED`、同一 PTS 时钟域内的证据范围、可信单调时钟观察/到期时间、已注册 adapter 与版本、前台快照和可回放的 student-action attestation。`UNKNOWN/AMBIGUOUS` 归属、过期事实、无 attestation、无时间线证据的伪 `DIRECT_PROGRESS_OBSERVED`、或不同会话/来源/许可的事实一律不得进入兴趣评估。

`InterestAssessment` 必须引用不可变 `SemanticScope`（含 scope hash、revision、semantic lineage），而非只携带字符串 `scopeId`。它保存已验签的 evidence-sufficiency profile、decision trace hash、评估单调时间和由策略给出的最小独立证据数；相同 `eventId`、动作 attestation 或分析观测 `observationId` 不得重复计数。`STUDENT_EXPLICIT` 是有 attestation 的主动行为；`ANALYSIS_OBSERVED` 可以代表同源屏幕流中可回放的暂停、回看、连续停留等事实，但必须有 adapter/version、前台快照、PTS 证据和 observationId，且单条弱观测不能独立确认兴趣。`SYSTEM_*` 永远不能作为兴趣正证据。`SAME_SCOPE` 必须使行为 PTS 范围落入目标 scope；`CONTINUOUS_SAME_EPISODE` 仅允许目标 scope 后、同一连续 episode、同一 lineage 且未超过该策略前序上下文窗口的事件。这保留学生继续看同一视频下一窗口时的正常 L1，而不允许任意旧弱信号拼接成兴趣。

兴趣和“值得学习介入”是两个判断：`InterestAssessment` 说明学生是否正在关注，`LearningOfferAssessment` 说明当前窗口能否形成有益且不过度打扰的学习简报。用户点击“不感兴趣”、关闭/忽略同类提示、禁用特定主题或设置安静时段，必须作为可撤销负反馈进入策略；它们不删除已有学习记录，但可抑制同主题的后续 heads-up。

### 3.3 实时快照与增量补全

L1 使用“当前稳定语义窗口”的版本化快照。兴趣达到门槛时，PC 立即生成并下发 `L1LearningBrief`；视频、图文或直播仍在继续时，L0 持续增加事实，PC 以同一 `episode_id` 发送增量修订。L2 图谱、L3 客观题和 L4 论证任务可在后续修订中补齐，不能成为第一条 L1 通知的前置条件。

`ContentEpisode` 是媒体连续边界，不是一次学习触达的去重单元。每次满足 L1 门时，受控账本必须以稳定 `learning_anchor_id` 创建或命中一个 `LearningMoment`；它绑定 learner/session/source/consent、semantic lineage 与稳定 `interventionKey`，并以 `LearningMomentRevision` 指向当时的 scope、兴趣、offer、brief 和证据。模型重跑、scope hash、package revision、interest assessment 或图谱 revision 改变都只能创建该 moment 的 revision，不能生成新的普通触达键；不同 episode 即使图谱复用同一概念也绝不合并 moment。

一条 episode 默认只预留一个普通 heads-up slot，但实际去重键属于 `LearningMoment`，不是 `scope`。后续修订只更新应用内 L1/发现记录；仅当出现不同的重大锚点，且学生已主动进入或明确订阅该类主题时，版本化策略才可原子预留第二个 slot。图谱联网补全、学生 patch、通知权限/OEM 阻断、scope/package 重投都不能解锁或退款普通 slot。学生已看到且实质错误的解释只可走单独限额的 `CORRECTION` 通知。

`InterruptionPolicy` 与 L1 本身分离：它根据最近活动会话、当前 episode 归属置信度、安静期和频率预算选择 `NOTIFY_NOW`、`DEFERRED` 或 `SUPPRESS_HEADS_UP_KEEP_IN_DISCOVER`。策略只控制打扰方式，不得丢弃 L1 简报，也不得回退使用旧 `current_visit` 规则。

`NOTIFY_NOW` 不能只依赖 PC 的历史 context snapshot。Android 必须先创建短时、一次性 `deviceDispatchNonce`，并在真正调用 `NotificationManager` 前于本机复核 nonce、前台/锁屏状态、episode/context relation、consent/fence 与 package revision；任一变化则只保留 Discover，不得补发 heads-up。通知默认使用锁屏最小披露：未解锁时不得暴露概念、摘要、来源、行为证据或图谱内容；用户显式开启后才可按其 Android 锁屏可见性设置增加内容。深链仍须经 `BriefAccessResolver`，通知文本绝不是访问授权。

### 3.4 L2 图谱的渐进生长与联网补全

生成 L1 时，系统立即在 `LearningMoment` 上建立当前内容图谱的**概念锚点**与证据范围。PC 的 `KnowledgeEnrichmentAgent` 以该锚点为检索任务，联网检索可引用的概念定义、上下位关系、事件背景、论证关系和例证；检索结果以带 `momentId` 的 `ContentGraphRevision` 增量合入当前内容图谱。L0 后续理解到的新事实也以同一 episode、同一或明确关联 moment 的 `ContentGraphRevision` 丰富或修正该图；它不重算兴趣、不创建 moment、更不触发普通通知。

该智能体是 PC 分析链的受控工具，不是手机聊天页的自由回答：

1. 它只能在 L1 已生成后补全 L2，不能决定兴趣、L1 资格或系统通知；
2. 每个外部节点/边必须保存来源 URL/标识、检索时间、证据摘录范围、模型与检索版本、支持或冲突状态；
3. 当前内容图谱可自动显示带“AI 联网补全”标记的增量；长期个人图谱/画像只接收学生确认或明确学习行为触发的可撤销写入；
4. 缺少可信来源、存在冲突或检索失败时保留 `PROPOSED`/`CONFLICTED` 状态，不把它写成确定事实，也不阻塞 L1 已有内容；
5. 外部网页、检索摘要和模型输出均是不可信输入，必须在边界解析、去指令化、来源/许可证策略和引用校验后才能形成 patch；来源策略更新同样要回归验证，不能以搜索排序或模型偏好充当可信度。

`KnowledgeEnrichmentAgent` 运行在低优先级独立队列：它不能占用 L0 的媒体理解 worker、不能拉低实时窗口水位，也不能因搜索失败阻塞 L1 或内容图谱本地修订。联网检索查询只发送最小必要、已脱敏的概念锚点和上下文，不发送原始媒体、完整转写或个人画像。

L2 页面展示的是 `ContentGraphRevision`：明确标注“来自本次内容”、当前补全状态、来源抽屉及 AI/学生修订标记。长期“知识全览”只展示 `PersonalEvidenceIndex`，它只可由学生的保存、确认、练习、复盘或明确图谱修订生成；内容图谱节点、L0 事实、联网结果和模型置信度都不得自动写入长期画像。

### 3.5 会话结束、撤回与删除

`CaptureSessionClosed`、`CaptureInterrupted`、`PauseCapture` 与 `DeleteRequested` 是不同事件。前三者只停止未来采集并按保留策略结算已获许可任务；其中 `CaptureInterrupted` 保留已封存媒体并对尾部窗口写入中断原因，`PauseCapture` 也不删除历史。`DeleteRequested` 才必须级联删除原始媒体、缓存、上传分片、PC 任务、outbox、Room 索引、L1/L2/L3/L4 派生包、来源摘录和个人索引，留下不含内容的 tombstone 与删除回执。每个删除请求都有单调递增的删除围栏代次：任何在删除前创建、但在删除后抵达的媒体、L0 fact、package、ACK、graph patch 或通知任务，都必须被 tombstone/fence 拒绝，不能因旧 token、离线重试或时钟差继续落库。跨端删除未 ACK 时不得继续分析、重试投递或联网补全。

### 3.6 实时服务等级与多设备时间

“实时”只在已标定的设备—模型配置上成立。`RealtimeServiceLevelPolicy` 必须为每个受支持配置记录**已批准的 p95/max 延迟、持续输入时长、输入/处理速率、最大队列深度、测量窗口、最小样本量、过载状态和降级动作**；没有已批准策略或没有满足该策略的同配置真机持续流报告，一律为 `NOT_REALTIME`。策略值来自真机持续流基准，不由产品文案硬编码，也不得把“记录了指标”当作通过门。

每个媒体源保存原始 PTS、单调时钟锚点、时钟域、同步样本、偏移/漂移估计和不确定度。跨手机、眼镜、PC 的事实只有在误差低于融合策略阈值时才可联合用于兴趣或图谱；超过阈值只能并列展示。

### 3.7 内容边界、音频与媒体安全

屏幕流不天然带有平台内容 ID。`EpisodeBoundaryResolver` 必须以范围哈希、连续 PTS、可解释的边界原因和策略版本创建、关闭、分裂或隔离 `ContentEpisode`；分屏、浮窗、内容切换、评论区、广告、时钟 epoch 重置或无法可靠归属时进入 `EPISODE_AMBIGUOUS`。歧义 episode 仍可保留 L0 质量事实，但不能进入兴趣评估、L1、内容图谱合并或长期索引。

“音频已采集”必须可审计地说明是受支持的播放音频、麦克风、混音还是不可采集，并记录采集 API/设备能力、应用限制、时间对齐误差、音轨连续性和失败原因。应用禁止播放音频捕获、DRM/系统策略限制或音画不同步时不得承诺“100% 成功”；系统必须显示可恢复原因并保持 `AUDIO_REQUIRED_UNRESOLVED`，直到关键语义得到合法、可核验的替代证据。

屏幕和音频媒体不能因位于局域网而视为可信。PC 本地与未来云端的媒体 data plane 都必须使用会话绑定的加密、双向身份验证、分片完整性与重放防护；明文 RTSP endpoint、可猜测路径或过期 session token 一律不得接收真实媒体。

### 3.8 正式作答与课后复盘

`FORMAL_ASSESSMENT` 是与日常兴趣链独立的 session mode。学生在已授权的纸笔试卷、教材任务或限时作答中，系统只记录任务上下文、题目/作答、第一视角、PC 行为与**状态质量线索**；不得弹出 L1、悬浮窗、练习、答案、提示、纠错或任何即时干预。进入该 mode 时，Android/PC/云必须原子取消或抑制该 learner 的所有待投、延后、重试中的 L1/practice/correction outbox，并记录 `FORMAL_ASSESSMENT_FENCE`；已显示通知必须取消且深链变为只读“作答中不可介入”，直到 session 结束。交卷或学生明确结束后，才进入 `POST_ASSESSMENT_REVIEW`：错误且过程证据充分的题目可给出概念解释/带答案示例；答对但过程不稳定的题目只建议无提示确认练习；证据不足或相互冲突的题目必须进入待复核，不能输出掌握结论。

正式作答的题目、教材和标准答案只能来自版本化、受控的 `CurriculumResource`。系统将题目—作答—证据—解释—建议组织为 `EvidenceCard`，清楚分离可观察事实、可能解释、反证/缺口、置信度、复核状态和建议动作。它不是对思维、医学、心理、人格或确定性专注度的诊断。

### 3.9 策略、完整性与多端治理

所有影响采集、外发、L1、通知、课程适配、内容安全、保留或删除的策略，必须来自可验证的 `PolicyBundle`：它具有签名/内容哈希、批准者、有效期、最低客户端/网关版本、撤销代次和回滚语义。每个事实、assessment、package、通知和删除 receipt 都记录实际采用的 bundle hash；签名无效、过期、被撤销或无法与当前运行时兼容时失败关闭，不外发、不形成 L1、不继续投递。策略升级如改变安全、授权、质量或课程适配结论，必须在投递前重新评估尚未呈现的包，不能靠旧缓存绕过新门。

每条可用于 L1、L3、L4、受控导出或竞赛验收的证据必须进入 `EvidenceIntegrityLedger`：从 capture range、事实、scope、package、学生操作到删除 receipt 形成可校验哈希链，并由设备/服务受控密钥签名。链断裂、签名不匹配或版本无法复现时，内容只可标为完整性未知/待复核，不能声称真实闭环或用于正式结论。

`PolicyBundle` 的验证根本身也必须受 `PolicyTrustRoot` 管理：初始根被固定在 Android/PC/网关受控配置中，轮换由当前有效根或独立紧急撤销根签名，包含 key epoch、过渡期、撤销列表和最小软件版本。未知根、回退到旧 epoch、密钥泄露后的 bundle 或无法验证撤销状态时失败关闭，不能把“能验证某个旧签名”视为当前可信。

`EvidenceIntegrityLedger` 必须定期产生 `LedgerCheckpoint`，将单调序列、链头、key epoch 和可信/不可信时间状态写入不可回退的本地安全存储，并在可用时与 PC/云 receipt 锚定。备份恢复、数据库回滚、设备换机或断网重放如无法证明 checkpoint 连续性，必须标为 `INTEGRITY_UNKNOWN/QUARANTINED`；本地设备不能证明的顺序，不得伪装成可信顺序。

实时 PTS 与策略墙上时间必须分开。`TimeAuthority` 使用 capture 的单调时钟为媒体顺序真源，并在 PC/云可用时校准可信时间锚点和时钟不确定度；用户可修改的墙上时间不能单独决定保留删除、quiet hours 解除、token 有效性或竞赛延迟。时间无法校准时，通知采取保守抑制，删除/到期进入可见待处理而非错误清除，验收报告明确时间可信度。

同一 learner 可同时拥有手机、眼镜、PC 等多个来源会话，但 `CaptureOwnershipLease` 必须按 source/session 控制重复采集，`LearnerDeliveryAuthority` 必须保证一条 L1 intervention 只由当前授权的主手机通知。切换主设备、撤销设备、离线恢复或多设备竞争都不能重复通知、串 scope 或让旧设备继续控制/读取。

## 4. 用户体验与数据归属

- 所有 L0–L4 内容均保留在应用内“发现”记录，通知只是 L1 的低打扰入口，不是发现页替代品。
- L1 采用 Android 系统高优先级消息样式，目标是类似微信/QQ 的 heads-up，而非仅通知中心历史记录；真实验收必须看见横幅且点击到正确内容包。
- 自动知识图谱由 PC 本地模型（未来可由正式云端网关）生成并下发手机。手工图谱保留为学生对 AI 图谱的修订能力，而非主要生成机制。L1 可先展示当前关系预览；完整 L2 图谱以同一 episode 的后续版本补全。
- 个人画像只沉淀可撤销的兴趣、查看、保存、练习与复盘证据索引。助手提出解释、选择与下一步，不代替学生操作第三方 App。
- 系统通知投递、自动打开、后台刷新、深链恢复、模型建议和 UI 曝光都不是兴趣行为。只有学生明确操作或经 `ObservationCapability` 证明的内容内行为才可进入 `BehaviorEvent`；`LearningActivity` 必须标记 `STUDENT_EXPLICIT`、`SYSTEM_DELIVERY` 或 `SYSTEM_RESTORE`，后两类绝不参与兴趣、画像或第二次触达的正向证据。
- 教师/研究者不是当前手机端账号、登录或监控后台。若竞赛/研究需要复核材料，只能由学生或授权管理者发起一个 scope-bound、脱敏的 `ControlledEvidenceExport`；导出内容、接收方、目的、到期和撤回均受审计，默认不含原始媒体、完整生理数据、聊天、浏览史或个人档案。
- L1 详情必须展示“为何出现这条学习承接”的最小证据类别、策略版本和当前抑制状态，并提供“稍后、不感兴趣、屏蔽主题、撤销屏蔽”入口；用户不能因为系统/OEM 的技术阻断而被标记为负反馈。

## 5. 设备与部署边界

| 条件 | 分析路径 | 不可违反的降级规则 |
|---|---|---|
| 已配对 PC | Android/眼镜连续媒体 → PC 本地模型 → 可靠 outbox → 手机 | `AnalysisRouteLease=PC_LOCAL_ACTIVE` 是唯一分析 owner。PC 中断只能转为 `PC_BUFFER_ONLY`；不得自动切换云端 |
| 无配对 PC | Android 通过与 PC 同构的 `AnalysisTransport` 调用团队云端网关 | 网关未部署/未验收时只允许 `CAPTURE_PENDING_ANALYSIS`；它不是面向无 PC 用户的可用交付。面向无 PC 用户发布前必须完成云端真机 L0→L1→撤回闭环，不得以聊天 API、mock 或本地假结果冒充完成 |
| 眼镜 | 第一视角视频源 → 与手机同一 episode/L0/L1/L2/L3/L4 领域状态机 | 现有项目没有真实眼镜采集适配器，页面/枚举不构成接入完成 |
| EEG/手表状态流 | 独立质量/连续性/伪迹与时间同步证据 → assessment/复盘的置信度输入 | 现有项目没有真实接入；不得输出医学、心理、人格、能力或确定性专注结论，也不得单独驱动手机 L1 |
| PC 独立学习 | PC 内容与任务流 → PC 本地分析与工作台 | 不要求先在手机出现兴趣；可与手机/眼镜证据在知识与时间轴层关联 |

PC 独立学习（网课、阅读、检索、写作、做题、项目）和纸笔/教材是独立 session 入口：它们分别使用 `PC_LEARNING` 与 `PAPER_TEXTBOOK` source，不通过手机兴趣门，也不强行映射为 Android heads-up。纸笔/教材首期可只实现最小会话与授权来源记录，但不能与手机屏幕流混用或称为已完成动作理解。

真实云链在 `CloudDataPolicy` 未冻结前只能实现 disabled/unavailable transport：任何媒体、转写、行为、图谱或个人索引均不得传出 PC/手机本地边界。正式云链必须先获得单独授权、数据 allowlist、短期认证/加密、保留期限、撤回级联删除、区域与审计契约，并以独立真机验收证明。若处理未成年人或状态流等敏感信息，启用前还必须完成适用的监护授权、最小必要和合规审查；该审查不由模型或普通 capture consent 代替。已配对 PC 的 session 不得因断连、云 grant 到达或服务恢复自动改为云 route；只有学生明确结束旧 session、旧 lease 收据化关闭且学生确认新 session 后，才可创建独立 `CLOUD_ACTIVE` lease。

撤回/删除同样覆盖冷备份、灾备副本、分析/指标聚合、搜索/向量索引、密钥材料和恢复流程。允许有保留期的不可变备份必须通过 per-session 加密密钥撤销立即失去可读性，并在下一次恢复前先应用删除 tombstone；不能把“备份暂未清理”写成删除完成。

现有手机“直连聊天 API”若存在，只是学生主动输入的独立智能体能力，不是 `CloudAnalysisTransport`：它不得读取 capture session、媒体、转写、L0 facts、兴趣、内容包、图谱或画像，也不得在 PC 断连时接管分析。只有未来受 `CloudDataPolicy` 控制的团队网关可承接无 PC 的学习分析链。

产品必须按 `capability-profiles.md` 的能力档位展示真实可用性。真实 Room/UI 接线、已配对 PC L0、已配对 PC L1、L2、正式学习、无 PC 云端、眼镜增强和竞赛证据是不同发布门；后续档位未完成时必须明确 unavailable，不能阻塞或冒充已经通过的前一档。

### 5.10 实施前必须封死的运行时边界

#### 5.10.1 不把 L1 变成全或无的传感器门

`EvidenceSufficiencyProfile` 按视频、图文、直播和当前语义对象定义真正必要的模态及可接受的组合行为证据。它解决的是“纯视觉内容因音频并非必要、或普通屏幕流没有播放器进度而永远没有 L1”的漏触达问题；它**不**允许降低授权、内容边界、内容安全、关键模态、稳定语义或证据可追溯性的硬门。每个 profile 必须版本化、可审计并经样本验证，不能把 90 秒、2/3、50% 或某个模型置信度写成跨内容的万能阈值。

#### 5.10.2 播放行为的真实来源

屏幕流不是第三方播放器 API。`VERIFIED_PLAYER` 仅在存在经许可、可回放的进度 adapter 时，才可形成自然结束、覆盖比例、倍速和 Seek 的精确事实；`SCREEN_INFERRED` 只产生带不确定度的屏幕级线索，`UNKNOWN` 不补猜。后两类可依 profile 与其他事实共同支持兴趣判断，但绝不能在 UI、通知或画像中伪造“已看完/看了 2/3”。没有适配器时系统必须如实展示观测能力，而不是为了满足指标假装识别了平台视频。

#### 5.10.3 运行时弃答、实时资源与当前上下文

离线 `SemanticQualityPolicy` 证明某设备—模型配置可发布，不等于每一个窗口都理解可靠。`RuntimeSemanticRiskAssessment` 对未知主题、关键模态冲突、覆盖不足和运行时质量退化采取 `ABSTAIN_L0_ONLY` 或复核；这样既不把不确定内容升级 L1，也不因非关键传感器缺席一概拒绝。

`ResourceGovernorSnapshot` 统一裁决手机电量/热、存储、网络、PC 推理队列和恢复条件。资源不足只能显式降为 L0、节流或暂停等待学生处理；不得隐形积压、静默丢弃封存证据或将降级链宣称为实时。每个 `L0_SEMANTIC_ACTIVE` session 还必须持续写 `L0SemanticHeartbeat`：若最新已 ACK 的语义 watermark 超过该设备—模型策略的 deadline，状态转为 `SEMANTIC_STALLED`，停止新 L1，UI 明示“采集仍在进行，理解端已停滞”；只有新、连续且满足 SLO 的 L0 batch 才可恢复。

高优先级通知还必须引用实时的 `DeliveryContextSnapshot`。`SAME_SCOPE` 与 `CONTINUOUS_SAME_EPISODE` 都属于当前相关：后者要求同一 learner/episode、PTS 连续、概念 lineage 仍相关、前台有效且归属可信，因此学生从已闭合概念窗口继续看同一视频下一段时仍可接到**该 episode 的一次** L1。只有学生已离开 episode、关系断裂、上下文过期或归属不明时才 `STALE/UNKNOWN`，简报保留在发现页并延后或抑制通知。不得把“必须仍停在原 scope”变成系统性漏触达，也不得用连续关系绕开一 episode 一次的通知预算。

#### 5.10.4 音频修复与学生可控性

`AudioCapabilitySnapshot` 只说明本次是否可采、同源性与有界音画同步；它绝不能单独推出“音频不重要”。只有独立的 `SemanticAudioRequirementDecision=AUDIO_NOT_REQUIRED_VERIFIED`，同时绑定同一 learner/session/source/consent generation、同一 PTS 范围、`NO_AUDIO_TRACK_VERIFIED` 的 absence proof，以及覆盖该语义窗口的视觉/文本与“音频非必要”证据，才可令 scope 使用 `AUDIO_NOT_REQUIRED`。没有该 decision 时一律是 `AUDIO_REQUIRED_UNRESOLVED`，不开放 L1。`AudioSupportMatrixEntry` 才说明某目标设备、Android 版本和内容应用组合是否经真机验证、失败原因和可执行恢复动作。未知/DRM/应用拒绝组合必须诚实降级为 L0，并显示恢复路径；不能承诺所有应用 100% 播放音频采集成功。

已配对 PC 断连时，Android 的每个封存分片必须先进入持久化 outbox，具有连续 `sequence`、PTS 范围、媒体与本地落盘 hash、outbox id 和重放幂等键。恢复 receipt 必须携带 ACK cursor、capture/route epoch、manifest 与 gap disposition；缺序、PTS 缺口、hash 改变或跨 generation 时隔离，禁止跨 gap 形成 stable scope/L1。endpoint 字符串相等仅是续传输入检查，不构成 route owner 的授权证明；唯一 owner 仍由 `AnalysisRouteLease` 解析。

后到 L0 事实只能先生成 `LateFactAdmission`：它必须绑定 source/consent/PTS、base scope revision/hash、事件水位、版本化允许迟到窗口、内容 hash 与幂等键。窗口内且未展示的 scope 只可重评；已展示 scope 只可修订或撤回；超窗、重放、前代不匹配、授权失效或跨 scope 的事实必须 quarantine。late fact 不得推进 watermark、恢复 heartbeat、直接生成 L1 或直接改写图谱。

学生可从 L1 查看该简报使用的语义与行为证据、管理主题/稍后/不感兴趣等未来打扰规则，并撤销自己主动沉淀到长期知识全览的条目。系统阻断、通知曝光或后台恢复永远不能伪装成学生偏好；控制个人画像不得破坏原始证据审计。

#### 5.10.5 适用处理资格与安全切换

普通屏幕采集授权不自动授权敏感信息、未成年人、云端分析或受控导出。系统以 `ProcessingEligibilityGrant` 记录**当前部署政策已判定**的处理类别、最小范围、授权主体类型、有效期和撤销代次；它不保存不必要的身份材料，也不自行判断法律年龄或监护关系。缺少、过期、撤销或无法验证该 grant 时，对应能力必须是 `UNAVAILABLE`：不外发、不恢复任务、不投递、不导出。具体适用规则由产品合规流程和版本化策略配置，而不是由模型或开发者猜测。

旧 candidate/visit 链切换 v2 时必须通过 `CutoverReleaseGate`。影子阶段只使用同一已授权证据 locator 对照 L0，禁止重复采集、系统通知、写长期画像或让影子结果影响学生；启用 v2 后旧链仅可只读迁移。若需要回退，只能停用 v2 投递并保留旧链只读展示，绝不能为了“恢复功能”重新打开 candidate 通知或旧兴趣判断。

在 lane worker 仍只能输出旧 `FusedCandidate` 的过渡期，`legacy_l0_adapter` 只可将 `CANDIDATE_ONLY` 窗口及其已核验 lane artifact hash 投影为 `LEGACY_FUSED_WINDOW_EVIDENCE_ONLY` 的 v2 `RealtimeSemanticFact`。该 adapter 不创建 `SemanticScope`、兴趣、L1、图谱或通知；缺少明确 learner/capture-consent/generation 的配置时必须关闭。它只是替换输入账本的只读迁移桥，不是对旧 candidate 重新授权。

#### 5.10.6 正式作答结束不是系统事件

`FORMAL_ASSESSMENT` 只能由学生显式 `ASSESSMENT_START_CONFIRMED` 或受控任务启动 receipt 进入；模型、画面或猜测的“像在考试”不能自行建立 fence。首期 `FormalAssessmentFence` 固定为 **learner-wide**：一名学生任一正式作答 session active 时，所有设备的 L1/practice/correction/自动深链均抑制；另一 task 或另一设备的 closure 不能解除它。Android Back、锁屏、前后台切换、进程死亡、网络断开和未确认离线草稿都只代表 `SUSPENDED` 或 `SUBMISSION_PENDING`，不能被实现为“已交卷”。只有同一 `assessmentId + learnerId + fenceGeneration` 的学生显式结束或交卷、可幂等回放的 `ASSESSMENT_CLOSURE_CONFIRMED` receipt 后，系统才可从 `SUBMITTED/ENDED_CONFIRMED` 进入 `REVIEW_READY`，解除 fence 并开始事后复盘；重复 close 不能重复发送答案、练习或通知。

#### 5.10.7 关键路径必须可访问，通知阻断必须可恢复

V5 的连接、L1 深链、证据抽屉、打扰/个人索引撤销、正式作答 fence 和通知 action 都属于学生的关键控制路径，必须有 TalkBack 语义、动态字体可读性、最小触控目标、确定焦点顺序和非颜色唯一状态；截图相似或 Compose 构建通过不构成可用。

`NotificationCapabilitySnapshot` 在通知尝试前和从系统设置返回后识别权限、应用/频道重要性、锁屏可见性、DND/OEM 阻断。可由学生修复的项目给出对应系统设置入口；不可由应用修复的阻断只说明原因且保留 Discover，绝不自动绕过系统设置或反复弹窗催促。

#### 5.10.8 模型、助手与评测的可信边界

每个进入 L0–L4、图谱、导出或竞赛材料的模型产物都必须带 `InferenceProvenance`：权重、prompt、预处理、采样/解码、运行时、输入范围、策略与随机性设置均可定位。仅写“使用某模型”不能复现，也不能支撑真实能力声明。

屏幕内容、语音、OCR/ASR、网页、附件和模型输出永远是数据，不是系统指令。媒体理解 worker 默认没有网络、凭据、设备控制、导出或通知投递能力；联网检索保持独立无凭据 sandbox，且只能补 L2，不能借由内容或网页改变 L0/L1、工具权限或学生策略。

助手只提出建议、解释和下一步，并以 `StudentActionProposal` 让学生逐次确认本应用允许的动作；它不得代替学生操作第三方 App、发送内容、改系统设置或借 Accessibility、ADB、后台服务、隐式 Intent/工具调用绕过确认。

质量回归和竞赛评价数据必须有 `EvaluationDatasetManifest`，按 episode、learner、来源和设备切分开发、验证与冻结测试。不能用同一学生/同一视频片段跨集合泄漏来调 prompt/阈值或证明性能；无许可证、未脱敏或已撤回的数据不得继续使用。

发现质量、安全、完整性或错误触达事故时，`SafetyCircuitBreaker` 立即将受影响范围降为 L0 审计或停止所有投递。熔断不能由模型自行恢复；恢复需要新的版本化策略、根因/样本证据、人工批准 receipt 和对未呈现内容的重新评估。

#### 5.10.9 实施顺序也是安全边界

任何会决定 L1、通知、正式作答、云端、导出或切换的硬门，必须在它所保护的功能进入生产路径前实现并以失败测试验证。任务编号、并行开发或 UI 演示不能构成绕过理由：未完成的前置门只能允许 unavailable/拒绝状态，不能用后续“补测”追认已经投递、已分析或已迁移的数据。

## 6. 验收场景

### 场景 A：手机视频的实时 L0 与 L1

学生授权屏幕采集并持续观看公开内容。Android 连续传输媒体与行为事实；PC 从连续窗口开始并行处理画面、语音、文字并记录 PTS、质量和语义增量。当前 `SemanticScope` 稳定闭合且形成足够的兴趣/学习介入证据后，PC 投递 L1 简报；手机原子落库后出现 heads-up，点击打开对应 L1。视频后续内容继续形成图谱、题目和论证修订，L2–L4 仅由学生继续进入。

### 场景 B：音频失败

视频画面到达但同源音频缺失、无效或无法对齐。若该窗口存在未解析的关键语音，系统保留 L0 质量记录并启动可见的故障恢复/重试，不生成 L1；只有同一范围的 absence proof、视觉/文本覆盖和 `SemanticAudioRequirementDecision` 共同审计证明音频不承载必要语义，才按 `AUDIO_NOT_REQUIRED` 的完整窗口规则继续判定。不能把采集失败、麦克风环境声或单独“无轨”伪装为无声内容。

### 场景 C：PC 断连

已配对 PC 在处理 episode 时断开。Android 将获许可数据写入本地缓存与传输 outbox，页面明确显示等待 PC 恢复；不切换云端，不丢弃已封存媒体。连接恢复后按 episode、分片序号、ACK cursor 与幂等键续传；发现缺片、PTS 缺口、hash/generation 不一致时隔离为 gap，不能把前后媒体拼成同一 stable scope。

### 场景 D：无 PC

无配对 PC 时，手机可选择云端分析路径。若团队云网关未配置，界面明确告知不可用并只保留 `CAPTURE_PENDING_ANALYSIS`；不得把采集/缓存称为 L0 已理解，不得发送伪造 L1。网关上线后必须使用同一消息契约完成真正端到端验收。

### 场景 E：通知被关闭或结果迟到

L1 简报已生成但 Android 通知权限/频道被关闭，或 PC 恢复后才投递结果。系统仍保存 L1 与发现页记录并 ACK 已持久化的包。前者不触发系统横幅；后者若学生已离开相关 episode，则不补发过期的高优先级横幅，只以应用内记录和用户可配置的摘要提醒呈现。不得因为不发 heads-up 而丢弃已生成的学习内容。

### 场景 F：边界、音频或安全门失败

学生在分屏、浮窗、广告或受限制应用间切换，或播放音频捕获被系统拒绝。系统记录可解释的边界/音频/安全质量状态，暂停外发或隔离为新 episode；不得把相邻内容拼为同一语义窗口、不得把麦克风环境音当作播放音频，也不得因此投递 L1。学生可在连接或发现页看到无内容泄露的原因与恢复动作。

## 7. 非目标与禁止项

- 不把 `CandidateCard`、`CANDIDATE_ONLY`、当前 visit 是否打开、三模态齐备或十秒新鲜度当作 L1 门。
- 不让旧 candidate/visit codec、ADB broadcast、receiver、fixture 或 shadow path 产生任何生产 L1/heads-up；它们只能服务只读迁移或隔离测试。
- 不把“完整内容”误写成“必须等整个视频结束”；L1 的完整性以当前连续语义窗口为单位，L2–L4 允许增量补齐。
- 不把模型生成的 L3 答案当作天然正确答案；每道客观题必须具有可追溯答案依据、独立校验状态和版本，无法校验时不开放 L3。
- 不把“内容有概念”视为“适合对该学生出题”。L3/正式复盘必须有当前 learner 的学段/学科/课程资源适配证据；无匹配受控资源时只保留 L1/L2，不生成泛化题目或错误的掌握结论。
- 不把单帧、关键帧、OCR 文本、模拟行为、离线回放、构建或单测说成实时端到端理解。
- 不默认上传、保存或声称保存云端原始媒体；云端生命周期待真实网关与用户许可策略一起落地。
- 不将眼镜、EEG、手表 UI 或图片视为真接入；状态设备不输出医学、心理、人格、能力或确定性专注诊断。
- 不以局域网、RTSP URL、设备 ID 或一次普通采集授权作为媒体加密、学生归属、未成年人/敏感处理授权或检索安全沙箱的替代物。

## 8. 需求追溯

- `C:\Users\Administrator\Desktop\华为杯\可行性材料\知行智学：项目汇报.pptx` 第 6、8、9、10、11、12、18 页：多端职责、兴趣入口、PC 本地中枢、L0–L4 和分阶段交付。
- 用户 2026-07-29 最终校正：实时 L0、兴趣型 L1、高优先级通知、L2/L3/L4 的精确定义、PC 断连缓存、无 PC 云接口和眼镜同构链。
- 反证审计补充 R78–R84：旧链零生产副作用、分析 route 唯一性、L0 双时钟停滞、连续 episode 上下文、正式作答 learner-wide fence、行为因果绑定与本机隐私投递。

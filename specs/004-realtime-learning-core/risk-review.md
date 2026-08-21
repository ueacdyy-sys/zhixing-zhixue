# 规格反思：L1 可达性与其余漏洞

## 已修正的 P0 漏洞

| 漏洞 | 原错误 | 修正后的规则 |
|---|---|---|
| 把 L1 等同全量包 | 要求整个视频、图谱、题目和论证都完成 | L1 只需要当前 `WINDOW_COMPLETE` 的 `L1LearningBrief`；L2–L4 增量补齐 |
| 把通知权限当作学习资格 | 用户禁用系统通知就没有 L1 | L1 永远写入发现页；权限只决定是否有 heads-up |
| 音频失败一刀切 | 纯视觉/无声内容永远不可能学习 | 区分关键音频未解析与已证实音频非必要；失败不得伪装成无声 |
| 删除 freshness 后无边界 | PC 恢复后可能对旧内容高优先级打扰 | 内容不丢；失去当前上下文时改为发现页/摘要，不补发过期 heads-up |
| 长视频重复通知或漏掉后续重大主题 | 每个窗口都可能弹一次，或整段视频只能一次 | `LearningMoment` 稳定去重；episode 默认一个普通 slot，只有不同重大 anchor 且用户主动进入/订阅才可原子取得第二个 |

## 仍须在实现中硬性解决的 P0/P1 漏洞

| 优先级 | 漏洞 | 实施约束 |
|---|---|---|
| P0 | 屏幕流没有平台视频 ID，不能可靠知道“正在刷哪一个视频” | 以 `ContentEpisode` 的媒体连续性、画面/音频/文本变化和 PTS 边界推断；边界不确定时不伪造平台 ID、不跨 episode 合并 |
| P0 | `WINDOW_COMPLETE` 未定义稳定性，局部模型摘要可能被误当完整理解 | scope 必须带 PTS 覆盖、模态质量、哈希、语义修订和事件时间水位；只有 `STABLE` scope 可 L1，后到冲突事实产生 `REVISED/INVALIDATED` 新版本 |
| P0 | 行为兴趣可能来自错误 episode 或不可观测的第三方 App 状态 | 区分 `ANDROID_OBSERVED` 与 `ANALYSIS_OBSERVED`；所有兴趣事实带 episode 归属置信度、PTS、观测方式、授权/前台状态；弱事件不得单独确认兴趣 |
| P0 | 兴趣被误当成值得学习介入，或用户已明确不想再被打扰 | 分离 `InterestAssessment` 与 `LearningOfferAssessment`；负反馈、主题屏蔽和安静时段进入 `InterruptionPolicy`，只抑制后续触达，不篡改历史 |
| P0 | 推理吞吐低于输入速率时，所谓实时会退化为积压 | 记录队列深度、输入/处理速率、端到端 PTS 延迟；允许模型级联和降采样策略，但不得静默丢弃已封存媒体或把积压说成实时 |
| P0 | L1 解释可能把视频观点写成事实 | 区分“视频可观察内容”“模型解释”“外部来源”；无法核验的解释必须显式标注不确定性，不作为个人画像或权威结论 |
| P0 | 联网补全把低质量网页、冲突信息或页面指令直接写入图谱 | `KnowledgeEnrichmentAgent` 只在 L1 后运行；外部内容按不可信输入处理，patch 强制保存来源、摘录、时间、版本和 `PROPOSED/SUPPORTED/CONFLICTED` 状态，不自动写入长期画像 |
| P0 | MediaProjection 可能采到私密页面 | 来源许可/禁止页过滤必须在传输前失败关闭；未知来源不得外发，不用 UI 说明代替技术门控 |
| P1 | 本地缓存无配额与撤回链 | 为媒体、事件、包和索引建立同一撤回/删除审计；空间水位触发受控暂停和明确提示，不得无声删证据 |
| P1 | 多设备/断连后的事件乱序使 L1 使用过期事实 | 所有事实保留 PTS、单调采集时钟、事件时间和水位；late event 只生成新 assessment/revision，不回写既有证据 |
| P1 | 直播没有结束、图文无标准进度 | 用语义窗口/主要内容阅读完成建模；需要真机样本标定，不把墙上时间硬编码成完成 |
| P1 | 自动图谱污染长期画像 | 内容图谱、学生编辑和长期证据索引分库/分事件；长期写入必须由明确学生行为或可撤销规则触发 |
| P1 | V5 示例图或现有自动投影被当作 L2 成果 | 生产 L2 只渲染 `ContentGraphRevision`；硬编码画布只留 debug QA，PC 自动关联不得同事务写入个人画像 |
| P1 | Android heads-up 不由应用绝对控制 | 通知渠道、权限、系统打扰模式都会影响展示；验收必须实机看见横幅，不以 API 返回或通知中心记录替代 |
| P1 | 包投递、PC ACK 和通知状态混为一件事 | 简报事务持久化后立即 ACK PC；通知通过独立持久 outbox 记录 `POSTED/BLOCKED/SUPPRESSED/OPENED`，避免无限重投或内容丢失 |
| P1 | 同一内容模型重跑/增量修订导致重复通知或新版永不提示 | 用 `LearningMoment` 的稳定 `l1InterventionKey` 去重、用不可变 moment/package revision 修订；scope hash、兴趣重评与图谱补全只更新 L1 页，不重开普通通知 |
| P1 | 无 PC/无云网关时把“已采集”当作“L0 已理解” | 显示 `CAPTURE_PENDING_ANALYSIS`；只有实际分析端产生 `RealtimeSemanticFact` 后才显示 L0 理解状态 |
| P1 | 联网图谱补全抢占实时资源或泄露不必要上下文 | 独立低优先级队列、预算和取消策略；查询只发送脱敏概念锚点，不发送原始媒体、完整转写或长期画像 |
| P1 | L3 自动题有答案但答案不正确 | 题目、答案、解析和判分规则均要有独立依据和校验状态；无法校验则不发布 L3 |
| P0 | 配对 bearer 被复制、长期有效或设备已解绑但 PC worker 继续运行 | 设备凭据放 Keystore；PC 只签发可轮换短 token；撤销同步停止 capture/lease/outbox/enrichment 并走删除链；用户停止是独立持久状态，服务重启不可绕过 |
| P0 | Android 分别写图谱 SQLite 与学习内容 SharedPreferences 后 ACK，造成半包、旧画像污染或无法按包删除 | v2 一律由同一 Room 事务写 package/brief/graph/outbox/receipt/去重；旧 inbox 只读迁移，不作为新链接收器 |
| P0 | MediaProjection 像素流无法可靠识别应用/视频，私密页过滤停留在 UI 文案 | 每 session 冻结用户选择的 system-share scope、目的地与 CapturePolicySnapshot；未知/敏感筛选失败关闭，不能声称获得平台 ID |
| P0 | “解除 PC”后手机仍可能在投屏、PC worker 仍可结算尾片或服务恢复轮询 | 解绑状态机依次停止用户 capture、停止/撤销 PC session、取消 lease/outbox、执行保留或删除策略、清除设备凭据；每步有可重试 receipt |
| P0 | 屏幕流被错误当作第三方播放器 API，伪造“看完/2/3/倍速/Seek/自然结束”行为 | 用 `ObservationCapability` 和 `ProgressEvidenceKind` 区分直接观测、弱线索和未知；未知只能参加带证据的兴趣策略，不得显示或依赖进度结论 |
| P0 | 模型以自报置信度或一次演示绕过语义正确性，错误概念进入 L1 | `SemanticQualityPolicy` 按设备/模型/输入建立标注回归集；事实支持率、遗漏、边界、误触达与更正率均需通过，版本变更强制失效重测 |
| P0 | 实时只记录指标但没有批准阈值，积压链仍可被宣传为实时 | `RealtimeServiceLevelPolicy` 必须带设备—模型配置、最小持续输入/样本、p95/max、吞吐、队列和批准报告；缺任一项为 `NOT_REALTIME` |
| P0 | 应用/DRM/系统拒绝播放音频或音画失配，却被误写为无声内容 | `AudioCapabilitySnapshot` 记录采集来源、设备/应用限制、同步误差和失败码；关键语义受限只留 L0，不能承诺 100% 采集成功 |
| P0 | 控制面 TLS 但媒体 RTSP 明文、可重放或被局域网其他设备接收 | `MediaSecuritySession` 要求加密、双向认证、分片 MAC、anti-replay、短期 endpoint/lease 与 scope 绑定；拒绝明文回退 |
| P0 | 分屏/浮窗/广告/切换把不同内容和行为拼进一个 episode | `EpisodeBoundaryResolver` 产生可解释边界；`EPISODE_AMBIGUOUS` 只留 L0，绝不进入兴趣、L1、图谱或画像 |
| P0 | `learnerId` 仅由业务约定，共享 PC/换机后跨学生读取、通知或删除 | 所有表/lease/envelope/revision/patch/resolver 使用 scope 复合约束和服务端授权；迁移仅可经显式 receipt |
| P0 | 联网 agent 被网页提示、私网 URL、Cookie 或压缩附件劫持 | 检索走无凭据 sandbox，禁止本地/私网/metadata，限制重定向/DNS/大小/解压/预算；失败不影响 L0/L1 |
| P0 | 无 PC 路径长期只有 unavailable，却被当作支持无 PC 用户 | 团队云网关、授权、配额、删除 receipt 与 Android 真机 L0→L1→撤回闭环为无 PC 发布门 |
| P1 | 风险内容或缺适用敏感/未成年人授权仍触发学习通知 | `ContentSafetyAssessment` 失败关闭；适用授权/监护授权未完成时 capability disabled，默认仅记录或复核 |
| P0 | 学生进入正式作答时，已排队/延后/重试/已显示的学习通知仍可打断作答 | `FORMAL_ASSESSMENT_FENCE` 跨端原子取消/抑制所有触达和深链；进程恢复、离线与 worker 重试不能绕过 |
| P0 | 授权撤回与在途媒体/包/ACK/patch 并发，旧消息在删除未完成时重新落库 | `ConsentFence` 使用单调 generation，在解析、事务、ACK、worker 和 resolver 前后拒绝旧 generation；只留无内容拒绝审计 |
| P0 | 系统点击/恢复/刷新被当作学生兴趣，形成自我强化的通知和画像 | `LearningActivityOrigin` 区分 `STUDENT_EXPLICIT` 与 `SYSTEM_*`；后者永不进入兴趣、画像和二次触达正向输入 |
| P0 | 内容修订/撤回后，旧 L1–L4 活动和离线答题被以新版本重新解释或给出最终分数 | Activity 固定不可变版本；离线 L3/L4 仅 pending/queued，联网重新核验 validation、课程对齐、scope 和 consent 后才最终化 |
| P0 | 通知 worker、撤回、click/delete PendingIntent 竞态导致重复投递、撤回复活或错误 dismiss | `NotificationAttempt` lease/nonce/dispatch generation 线性化；事件优先级 `CANCELLED_REVOKED > OPENED > DEFER_BY_USER > DISMISSED` |
| P1 | 冷启动深链在 Room 未就绪、撤回、过期或 scope 错误时显示 fixture/错误内容或 Back 退出 | `BriefAccessResolver` 明确拒绝状态与 Discover 父级；所有异常状态有进程死亡回归 |
| P0 | 策略版本字段可被替换、过期或回滚，旧缓存绕过新的安全/授权/质量门 | `PolicyBundle` 签名、有效期、撤销代次、兼容 profile 和未呈现包重评；无效 bundle 失败关闭 |
| P0 | 证据日志或 receipt 被篡改/断链，却被用于竞赛或正式学习结论 | `EvidenceIntegrityLedger` 从媒体到删除 receipt 连续签名；断链/重放 quarantine，不得称真实闭环 |
| P0 | 多手机/眼镜/PC 竞争同一 source 或旧设备仍投递 L1 | `CaptureOwnershipLease` + `LearnerDeliveryAuthority` epoch；不同 source 可并行，同一 source/通知唯一 owner |
| P0 | 删除只清在线数据，冷备份、DR、索引、聚合或恢复流程重新暴露内容 | `BackupDeletionManifest`、per-session key revocation、恢复前 tombstone fence；未完成只能 pending/escalated |
| P0 | 客户端/网关不兼容时字段猜测或降级使用旧 candidate 链 | `ProtocolCompatibilityProfile` 签名协商；仅升级/不可用，绝不 protocol downgrade |
| P0 | PolicyBundle 有签名但信任根被替换、回退或泄露后仍被当作可信 | `PolicyTrustRoot` 管理 root epoch、轮换、紧急撤销和最低版本；根状态不可验证即失败关闭 |
| P0 | 哈希链存在但本机/备份回滚后重新从旧链继续，伪造连续证据 | `LedgerCheckpoint` 写入不可回退安全存储并可跨端锚定；连续性无法证明即 quarantine，禁止正式声明 |
| P1 | 用户调整墙上时间使 quiet-hours、token、删除或竞赛延迟被误判 | `TimeAuthority` 分离 PTS/单调顺序与可信墙钟；时间不可信时不打扰、不误删、可见待校准 |
| P0 | 设备 ID、PC pairing 或历史迁移被当作学生身份，多学生数据串入画像、通知或删除范围 | 引入 `LearnerScope`；所有主键/lease/evidence/删除按 learner 隔离；云端另需显式认证 subject，无法归属的旧数据 quarantine |
| P0 | 撤回后系统通知仍可点击、删除无限 pending 或失败被静默吞掉 | 删除任务带 deadline/receipt/escalation；取消 Android NotificationManager 项与 deeplink/cache；逾期状态对用户可见且禁止读取 |
| P0 | 既有手机直连聊天 API 被误接为无 PC 的媒体/兴趣分析后门 | 在类型、权限与网络层隔离聊天与 `CloudAnalysisTransport`；聊天无 capture/graph/profile scope，PC 断连只能缓存 |
| P0 | 将 L1 的每一项质量条件机械相乘，纯视觉/图文或缺少播放器 API 的真实学习内容永远无法触达 | `EvidenceSufficiencyProfile` 按内容模态定义充分证据与可用组合，保留语义/授权/边界/安全硬门；禁止固定时长或所有传感器齐备的一刀切 |
| P0 | 屏幕推断被写成自然结束、2/3 覆盖、倍速或 Seek，系统虚构第三方播放器事实 | `ObservationTier` 强制区分 `VERIFIED_PLAYER/SCREEN_INFERRED/UNKNOWN`；只有经许可 adapter 的可回放证据能产生精确进度 |
| P0 | 通过离线回归的模型在未知领域、模态冲突或质量退化窗口仍自信输出 L1 | 每个 scope 必经 `RuntimeSemanticRiskAssessment`；非 CLEAR 只能 L0 或复核，不能以模型置信度绕过 |
| P0 | PC 延迟后学生已刷到下一内容，旧 L1 仍以高优先级通知打断 | `DeliveryContextSnapshot` 必须在投递前后匹配同一 episode/scope；过期只留发现页、延后或抑制 |
| P1 | 每视频实时理解忽略手机电量/热/存储、网络和 PC 队列，最终积压、发热或静默丢证据 | `ResourceGovernorSnapshot` 显式 NORMAL/降级 L0/节流/暂停；恢复重新验 SLO，不完整链不称实时 |
| P1 | “尽量修复音频”没有面向目标设备与内容应用的实测支持清单，最终把不可采误报为可用 | `AudioSupportMatrixEntry` 记录组合、限制、同源同步样本、恢复动作和失效；未知/DRM/拒绝只如实降级 |
| P1 | 学生无法知道系统为何打扰、怎样撤销长期沉淀，画像即使不诊断也可能不可控 | L1 证据抽屉、可撤销打扰规则和 `PersonalEvidenceIndex` 撤销为强制 UI/领域路径；系统行为不得成为正向画像 |
| P0 | 普通 capture consent 被错误扩大为敏感、未成年人、云端或导出处理授权，或者设备/历史信息被拿来猜测监护资格 | `ProcessingEligibilityGrant` 按部署政策记录最小资格结论；缺失/过期/撤销在 ingress、恢复、投递、导出均失败关闭，不自行推断年龄/监护关系 |
| P0 | v2 灰度失败后为“恢复通知”而复活旧 candidate/visit 链，造成同一学生双链、重复媒体或错误 L1 | `CutoverReleaseGate` 规定影子只做无副作用 L0 对照；回退只可停 v2 投递、旧链只读，永不重开 candidate 通知/旧 JSON 写入 |
| P0 | 资格 grant 只存在内存或普通 consent 附注，进程恢复/跨端重放后敏感处理被错误恢复 | `ProcessingEligibilityGrant` 持久化且 scope/generation 绑定；所有 ingress、恢复、通知、云端和导出走同一 resolver，过期/撤销失败关闭 |
| P0 | 正式作答因 Back、崩溃、锁屏或网络断开被误当结束，fence 提前解除并给出答案/复盘 | `AssessmentSession` 显式 ACTIVE/SUSPENDED/SUBMISSION_PENDING/SUBMITTED/ENDED_CONFIRMED/REVIEW_READY；只有 closure receipt 可解 fence |
| P1 | Compose 页面视觉可用但 TalkBack、动态字体、焦点、触控或非颜色状态不可达，学生无法完成 L1–L4 和撤销 | 把 Semantics、动态字体、最小触控目标、焦点与可读通知 action 写入 UI 基线并真机验收 |
| P1 | 通知被权限、频道、DND 或 OEM 阻断后，学生没有原因、修复入口或返回检测，只会误以为系统失效 | `NotificationCapabilitySnapshot` 提供可修复设置入口和不可绕过说明；Discover 始终保留，不自动绕过/催促 |
| P0 | 同一“模型版本”在不同 prompt、预处理、采样或运行时下得到的结论无法复现，却被用于正式/竞赛声明 | `InferenceProvenance` 记录完整不可变配置和输出 hash；缺失即禁止 L1/L3/L4、导出和能力主张 |
| P0 | 视频文字、语音、OCR/ASR、网页或模型输出被当成指令，诱导 worker 访问网络、凭据或控制设备 | `ModelExecutionCapability` 最小授权；媒体理解默认无网络/工具/设备/导出权限，检索结果只可补 L2 |
| P0 | “私人助手”在未确认下替学生操作第三方 App、发送内容或修改系统设置 | `StudentActionProposal` 强制逐次可见确认、白名单与审计；禁止 Accessibility/ADB/隐式 Intent/后台绕过 |
| P0 | 语义质量或竞赛性能用同一 episode/learner/设备跨开发和测试泄漏获得，或使用无许可证数据 | `EvaluationDatasetManifest` 冻结切分、许可证/脱敏/标注协议和撤回门；泄漏样本不能作为通过证据 |
| P0 | 错误触达、安全事故或完整性问题发生后仍继续 L1/L3/L4 投递，等待模型自行恢复 | `SafetyCircuitBreaker` 立即停受影响介入，恢复需根因、重验、新策略和人工批准 |
| P0 | 新增硬门任务排在 L1/通知/迁移实现之后，团队按编号或演示压力绕过前置验证 | `plan.md` 的 G1–G6 依赖门和 `CapabilityProfile` release gate 强制前置；未完成只能 unavailable/拒绝，不能补测追认 |
| P0 | 旧 Candidate dispatcher、广播 receiver 或 PC inbox 仍能绕过 v2 规则直接产生系统通知 | v1 dispatcher 固定只读，Manifest 不导出 receiver，receiver/inbox 无通知副作用；仅显式离线迁移 reader 能读取旧数据 |
| P0 | PC 断连、云资格到达或恢复时同一 episode 双端分析/旧缓存出域 | `AnalysisRouteLease` 是 session 的唯一 owner；PC 只可 buffer，云只能在旧 session 收据化关闭后由学生确认的新 session 建立 |
| P1 | capture 仍存活但 L0 worker 卡死，页面继续冒充实时理解 | `L0SemanticHeartbeat` 使用已处理媒体 watermark 与 worker health 双时钟；deadline 过期为 `SEMANTIC_STALLED`，禁新 L1、迟到包只进 Discover |
| P1 | 同一视频连续下一 scope 被“同 scope”门误抑制，或 scope hash 去重导致长视频重复通知 | `SAME_SCOPE/CONTINUOUS_SAME_EPISODE/STALE` 关系和 episode 级默认通知预算；连续关系须无 gap、PTS/lineage/前台/归属同时成立 |
| P0 | 正式作答 fence 能被模型猜测建立，或被另一设备/任务的结束回执解除 | 固定 learner-wide `FormalAssessmentFence`；只接受启动 receipt 和同 assessment/learner/generation closure receipt |
| P0 | 两条旧弱信号、跨会话行为或伪造的 `STUDENT_EXPLICIT` 被拼成兴趣，进而错误触发 L1 | `BehaviorEvent` 绑定 session/source/consent/PTS/单调到期/registered adapter/action attestation；assessment 绑定 immutable scope/lineage，按 profile 去重独立证据 |
| P0 | PC 判断仍相关但 Android 实际投递时已切内容、进入正式作答或锁屏泄露学习内容 | `deviceDispatchNonce` 本机二次复核 context/fence/revision；失败仅 Discover，锁屏默认 `MINIMAL`，点击不绕过 resolver |

## 关键语义边界

“完整语义理解”有两个层次：对当前连续语义窗口，达到 `WINDOW_COMPLETE` 后可即时形成 L1；对整条视频/图文/直播 episode，达到 `EPISODE_COMPLETE` 后才形成最终汇总、完整图谱和后续学习内容。若坚持把两者合并，系统只能等播放结束，与实时低打扰触达不可同时成立。

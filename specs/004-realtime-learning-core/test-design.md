# 测试设计与验收 Oracle

| 编号 | 场景 | Oracle（可判定结果） | 证据 |
|---|---|---|---|
| TD-01 | 持续视频 L0 | 每个事实批次持久化、可重放、PTS/哈希/质量完整 | PC/Android ledger 与 ACK |
| TD-02 | L1 中途触达 | stable scope 未到 episode 结束即产生 canonical package brief；仅一条通知 | revision、outbox、真机深链 |
| TD-03 | 关键音频失败 | `AUDIO_REQUIRED_UNRESOLVED`，无 L1；无声正例必须有非必要音频审计 | 媒体轨/质量日志 |
| TD-04 | 断连和乱序 | 同 episode 续传；late fact 仅新 revision；缓存满受控暂停。相同 fact/admission 重放幂等，冲突载荷、gap、前代/展示状态不符均拒绝，late fact 不推进 watermark | cursor、watermark、不可变 ledger、状态日志 |
| TD-05 | 授权撤回 | 各端删除目标均 receipt；tombstone 后无法再展示/分析 | 删除任务与负向读取测试 |
| TD-06 | 通知 | A: Room 持久化+NotificationManager 提交；B: 基准真机/已开权限频道/DND 前提下可见横幅和正确深链 | outbox、设备录像、系统状态 |
| TD-07 | 图谱生长 | L1 锚点→内容图谱 revision→联网 patch；来源/冲突可见，student patch 不丢 | revision DAG、来源抽屉、patch rebase |
| TD-08 | 长期索引 | 未主动学习的内容图不进入长期页；保存/练习/复盘可撤回 | `PersonalEvidenceIndex` 查询/撤回 |
| TD-09 | L3/L4 | L3 每题有非同生成器的依据/校验者；失效即下架；L4 有回执 | validation record、UI 状态 |
| TD-10 | PC/纸笔独立入口 | 不经 Android 兴趣也能建 session、证据和工作台路径 | PC session 日志、独立 UI 验收 |
| TD-11 | 云不可用/已启用 | 未配置只显示 pending；正式云链须有 consent、allowlist、删除 receipt | capability、网络审计 |
| TD-12 | 实时 SLO | 每个受支持设备—模型配置有持续流输入、p50/p95/max、队列水位、过载状态；超限不得称实时 | 基准报告与原始日志 |
| TD-13 | 打扰与负反馈 | 系统阻断、dismiss、稍后、明确不感兴趣、主题屏蔽、撤销和更正提醒各自按 policy 状态迁移 | policy snapshot、outbox、负向断言 |
| TD-14 | L3 校验撤销 | 同一生成器不能单独验证；依据/校验器撤销后题目下架，旧作答只读审计 | validation record、题目版本、UI 回归 |
| TD-15 | 云数据边界 | disabled 时网络零出域；启用后只允许 policy allowlist，撤回生成跨端 receipt | Android/网关网络审计、删除日志 |
| TD-16 | 旧链迁移 | 映射数/hash、quarantine、patch 回放、只读回退和删除门均通过 | migration report、导出、回归日志 |
| TD-17 | PC/纸笔独立入口 | 不经 Android 兴趣即可创建 session、保存来源/许可、进入工作台并回执 | PC 日志、独立 UI 验收 |
| TD-18 | 本地保留与设备撤销 | 公共目录/通知无原始内容；到期清理有 receipt；撤销配对后无媒体、控制或未完成 lease | 存储审计、密钥/lease 日志、负向网络测试 |
| TD-19 | 配对与用户停止 | token 过期/重放/撤销失败关闭；解绑立即终止 PC worker/lease/outbox；START_STICKY 或重连不绕过用户停止 | Android/PC 审计、进程重启和网络恢复日志 |
| TD-20 | 原子包投递 | 在 package、图谱、通知 outbox、receipt 任一写入点注入失败；无 ACK/无半包，可用同一修订安全重投 | Room transaction、PC ACK/NACK、负向读取测试 |
| TD-21 | 捕获范围与私密过滤 | system single-app 与 whole-screen 都有 policy snapshot；未知/敏感过滤器不确定时不外发 | Android sender/PC ingress 日志、网络负例 |
| TD-22 | 解绑事务 | 解绑时 MediaProjection、RTSP、PC worker、lease/outbox 按顺序终止；中断后可重试且无残留恢复 | 双端 receipt、进程重启、网络恢复日志 |
| TD-23 | 进度观测能力 | 无平台 API/可读进度证据时不得生成看完、覆盖、倍速或 Seek；直接进度证据可重放核对 | evidence range、capability snapshot、领域负例 |
| TD-24 | 语义质量发布门 | 新模型/prompt/模态/检索版本在同一标注集回归；未过质量门不能产出 L1 | versioned report、样本分层、L1 负向验收 |
| TD-25 | 学生 scope 隔离 | 共享 PC、换手机、跨 scope token/ACK/evidence/删除/迁移均失败关闭；仅显式绑定可访问 | DB constraint、gateway 403、迁移 quarantine 报告 |
| TD-26 | 删除终态与通知撤销 | 撤回后系统通知取消，深链/缓存不可读；不可达 target 到 deadline 后进入可见 escalation | NotificationManager、receipt、tombstone、断网重试日志 |
| TD-27 | 眼镜来源 | 真实眼镜媒体、授权、时钟锚点和误差在独立 source session 可回放；未接入不得显示为可用 | 设备录像、PTS/clock mapping、不可用 UI 负例 |
| TD-28 | 禁止诊断 | UI、导出、图谱、智能体输入/输出均不生成医学、心理、人格、能力或确定性专注结论 | 静态扫描、契约拒绝、人工 UI/导出复查 |
| TD-29 | 同次真实闭环证据包 | 同一 capture session 的授权、媒体 hash/PTS、L0、L1、Room receipt、通知提交/基准横幅、点击和降级状态可关联 | session ledger、设备录像、系统状态、PC/Android 审计 |
| TD-30 | 直连聊天隔离 | 无 PC/PC 断连时聊天 API 不接收任何 capture/episode/fact/package/graph/profile，不能产生 L0/L1 | 网络请求审计、权限拒绝、断连负例 |
| TD-31 | 正式作答 mode | 作答期间 notification/practice/intervention outbox 全部拒绝；结束后才允许按题目/证据生成 review card | 双端 outbox、会话时间线、负例与复盘卡 |
| TD-32 | 证据卡与课程资源 | 事实、解释、反证、缺口分离；L3/复盘答案只引用版本化受控资源，资源变更产生新 revision | schema、资源许可证、review 回放 |
| TD-33 | 增强状态流 | EEG/手表/眼镜质量或时钟超限时不参与融合；状态流不能单独生成诊断或 L1 | source adapter、时钟/伪迹日志、策略负例 |
| TD-34 | 受控导出 | 字段 allowlist 外的数据不能导出；接收方、到期、撤回和下载拒绝均可审计 | export receipt、链接撤回、内容扫描 |
| TD-35 | 竞赛验证画像 | 时间轴、事件 F1/误差、κ、证据卡、降级、复盘延迟均按同配置报告；能力等级与证据一致 | 原始日志、标注集、对照/消融、错误案例、声明审计 |
| TD-36 | 实时 SLO 发布门 | 每个设备—模型配置必须有批准策略、持续输入时长、最小样本、p95/max、吞吐、队列与过载日志；缺任一项为 `NOT_REALTIME` | 策略快照、同配置原始 benchmark、状态转换负例 |
| TD-37 | 音频能力和同步 | 播放音频、麦克风、混音、应用限制、DRM/系统拒绝和音画失配均形成 `AudioCapabilitySnapshot`；关键音频受限无 L1 | 设备/应用矩阵、同步误差日志、L1 负向断言 |
| TD-38 | 媒体安全会话 | 未认证、过期、明文、重放、MAC 错误、跨 learner 分片和可猜测 endpoint 均拒绝；有效会话可幂等续传 | 握手/分片审计、密钥零泄露检查、网络负例 |
| TD-39 | 内容边界歧义 | 分屏、浮窗、广告、评论区、内容切换、PTS epoch 重置和跨时钟超限均生成可解释边界；歧义不得参与 L1/图谱合并 | boundary ledger、episode 隔离回放、兴趣/L1 负例 |
| TD-40 | 无 PC 云端闭环 | 有效云 consent/scope/配额下，Android 真机完成云端 L0→L1→撤回删除；未部署时仍只显示 unavailable | 真机录像、网络 allowlist、云删除 receipt、无 mock 证明 |
| TD-41 | 强制 scope 隔离 | Shared PC、换机、缓存恢复、ACK、deep link、patch、export、delete 的跨 learner 操作全部拒绝；显式 transfer 才能迁移 | DB/FK、403、scope transfer receipt、负向读取测试 |
| TD-42 | 检索沙箱 | 私网/metadata/重定向/DNS 重绑定、Cookie、提示注入、超大/压缩附件与恶意网页均不触达内部资源且不影响 L0/L1 | fetch audit、网络隔离日志、图谱无写入断言 |
| TD-43 | 安全与适用授权门 | 风险内容只记录/复核，不 heads-up；敏感/未成年人/云端所需授权未满足时不采集外发/不介入 | policy 回归、capability disabled、通知 outbox 负例 |
| TD-44 | 正式作答打扰栅栏 | mode 切换时 pending/deferred/retry/posted L1、practice、correction 均取消/抑制；进程恢复不绕过 | 双端 outbox、NotificationManager、session timeline、负例 |
| TD-45 | 撤回 generation 竞态 | 在 ingress、事务、ACK、notify 前后、缓存恢复和 patch 投递注入撤回；旧 generation 无内容落库或副作用 | ConsentFence、tombstone、worker/lease 日志、负向读取 |
| TD-46 | 系统活动因果隔离 | 通知提交、自动打开、深链恢复、后台刷新、迁移均为 `SYSTEM_*`，不能提升兴趣/画像/二次触达 | activity ledger、assessment/profile 查询、策略负例 |
| TD-47 | 课程适配门 | 学段/学科/资源不匹配或撤销时 L3/课程性复盘 unavailable；旧作答保持版本审计 | CurriculumAlignment、question validation、UI/判分负例 |
| TD-48 | 通知投递线性化 | worker crash、撤回与 notify 并发、重复 PendingIntent、click/delete/snooze 并发不重复投递、不误记 dismiss | NotificationAttempt lease/nonce、系统日志、策略状态 |
| TD-49 | 版本化学习活动与深链 | L1–L4 activity 固定版本；修订/撤回/迁移后深链只显示正确 access state，冷启动 Back 返回 Discover | version ledger、BriefAccessResolver、进程死亡 UI 回归 |
| TD-50 | 离线 L3/L4 对账 | 离线答案/论证仅 pending/queued；恢复后才 final/delivered，撤销/课程不适配/scope 错误拒绝且不入长期索引 | offline store、reconciliation receipt、历史审计 |
| TD-51 | 策略 bundle 治理 | 签名无效、过期、撤销、版本回滚、不兼容及安全策略升级时失败关闭；未呈现包重评 | bundle verifier、policy hash、outbox/transport 负例 |
| TD-52 | 证据完整性链 | 同一 session 从媒体到 L1/L3/L4/导出/删除的 hash/signature 链可验证；断链、篡改、重放 quarantine | ledger proof、key verification、能力声明负例 |
| TD-53 | 多设备所有权与投递权 | 同源竞争、旧 device epoch、换机、撤销、离线恢复只能有一个 owner；同 intervention 只有主手机投递 | ownership/authority leases、notification attempts、跨端拒绝日志 |
| TD-54 | 备份删除与恢复 | 备份、DR、索引、聚合、对象密钥均进入 manifest；恢复前强制 replay tombstone，未完成不可报删除成功 | backup manifest、key revocation、restore simulation、escalation receipt |
| TD-55 | 协议兼容 | 老客户端/网关、未知 schema/能力、bundle 不兼容均拒绝并提示升级；无 candidate/card 降级 | compatibility profile、network traces、negative integration |
| TD-56 | 策略信任根 | 根轮换、紧急撤销、过渡期、epoch 回退、未知/旧 key、最低软件版本均按签名链失败关闭 | trust-root receipts、bundle verifier、upgrade/deny logs |
| TD-57 | 账本检查点 | DB/备份回滚、换机、离线重放、旧 key 和远端 receipt 缺失导致 integrity unknown/quarantine，不得称已验证 | checkpoint proof、secure-store/anchor logs、导出/声明负例 |
| TD-58 | 时间可信门 | 墙钟回拨/跳变、无网络、校准恢复和 PTS 正常时，媒体顺序不乱；通知保守抑制、删除/token/竞赛指标不误判 | TimeAuthority trace、policy decisions、retention/notification negatives |
| TD-59 | 能力档位与 UI | Room/UI 只显示当前真实 `CapabilityProfile`；本地 L0/L1、云、眼镜、正式学习、竞赛各自升级/降级，前一档不被后续未接入阻塞 | profile reducer、UI 状态、报告能力等级、fixture/candidate 负例 |
| TD-60 | 分类型证据充分与观测来源 | 视频/图文/直播按 profile 选择必要模态；纯视觉正例可走 `AUDIO_NOT_REQUIRED`，无播放器 API 不伪造进度，verified adapter 的范围可回放核对 | profile snapshot、adapter evidence、领域/真机负例 |
| TD-61 | 运行时语义弃答 | 未知主题、关键 ASR/OCR/VLM 冲突、覆盖不足和质量退化均为 `ABSTAIN_L0_ONLY/REQUIRE_REVIEW`；恢复只能新 revision 再评估 | risk assessment、scope revision、L1 负向断言 |
| TD-62 | 当前上下文通知 | brief 生成后刷走内容、锁屏/切应用、nonce 改变、snapshot 过期或迟到包时不发 heads-up；brief 仍在 Discover 可达 | context snapshot、outbox、NotificationManager、深链日志 |
| TD-63 | 资源仲裁与恢复 | 低电量、热、空间、网络、PC 队列过载进入指定降级/节流/暂停；无静默丢片、无不完整 L1、恢复重新过 SLO | governor trace、PTS ledger、SLO 报告、用户状态截图 |
| TD-64 | 音频支持与恢复矩阵 | 每个已声明支持组合有同源播放音频与同步样本；DRM/应用拒绝/失配/未知组合仅 L0 并展示恢复原因 | matrix record、真机日志、同步误差、L1 负例 |
| TD-65 | 学生可解释与可撤销控制 | L1 可展示证据类别与来源；撤销 topic/个人索引即时影响未来策略、不改写历史；系统阻断不成为偏好 | UI 回归、policy/index audit、后续通知负例 |
| TD-66 | 适用处理资格 | 敏感/未成年人/云端/导出按当前部署政策要求 grant；普通 capture consent、设备/历史信息不可替代；过期/撤销后 ingress、恢复、投递、导出均拒绝 | grant audit、envelope/DAO/worker 负例、capability unavailable UI |
| TD-67 | v2 受控切换 | shadow 仅复用已授权 evidence 做无副作用 L0 对照；active 有签名 release receipt；回退只停 v2 投递、旧链只读且 candidate 通知永不复活 | cutover ledger、媒体/通知/画像审计、迁移与回退回归 |
| TD-68 | 资格 grant 持久化 | `ProcessingEligibilityGrant` 在 Room/网关持久化并与 learner/generation 绑定；进程死亡、恢复、跨 scope、过期/撤销和普通 consent 冒充均拒绝 | DAO/FK、resolver、worker/ingress/导出负例 |
| TD-69 | 正式作答生命周期 | `AssessmentSessionState` 在 Back、锁屏、崩溃、断网、未确认离线草稿和重复 close 时保持 fence；仅显式交卷/结束 receipt 进入 review，且不重复恢复触达 | session ledger、outbox、NotificationManager、进程恢复回归 |
| TD-70 | 无障碍路径 | TalkBack/语义树、动态字体、焦点、触控、非颜色状态和通知 action 覆盖连接、L1、证据抽屉、撤销与正式作答 fence | Compose UI test、accessibility scan、基准真机手工路径 |
| TD-71 | 通知能力恢复 | 权限、频道、锁屏、DND/OEM 各自形成 `NotificationCapabilitySnapshot`；可修复项跳系统设置并返回刷新，不可修复项不催促，Discover 永远可达 | provider log、设置跳转/返回、NotificationManager、UI 回归 |
| TD-72 | 推理可复现性 | L0/L1/L2/L3/L4/导出产物均能由 `InferenceProvenance` 复现权重、prompt、预处理、采样、运行时、输入范围和输出 hash；缺失任一项拒绝正式使用 | provenance store、codec/Room 负例、复现实验 |
| TD-73 | 媒体提示注入与最小权限 | 屏幕/语音/网页/模型输出不能改变 worker 工具、网络、凭据、设备、导出或通知权限；检索只能产生 L2 修订 | sandbox/worker logs、权限拒绝、网络负例 |
| TD-74 | 助手操作确认 | 未确认、拒绝、过期、跨 scope 或第三方目标 proposal 不执行；Accessibility/ADB/隐式 Intent/后台 service 不能绕过逐次确认 | proposal receipt、intent/tool deny log、UI/服务回归 |
| TD-75 | 评测数据治理 | 同一 episode/learner/来源/设备不得跨开发与冻结测试；无许可证/已撤回数据和测试集调参均被拒绝 | manifest、split/leak detector、许可证/撤回审计 |
| TD-76 | 安全熔断与恢复 | 质量/安全/完整性/错误触达事件打开 breaker 后停止受影响 L1/L3/L4/通知/导出；进程恢复和模型不能自闭合，人工恢复后重评未呈现包 | breaker ledger、outbox/export logs、recovery receipt |
| TD-77 | 实施依赖门 | G1–G6 任一前置未通过时，后续生产 wiring、通知、云/导出、正式复盘、旧链删除与回退均拒绝；fixture/shadow/debug 不得绕过 | capability/release report、feature wiring、迁移/通知负例 |
| TD-78 | 旧链通知封锁 | 合法 v1 candidate、ADB broadcast、PC inbox、receiver、fixture/shadow 均不产生 Discover 新内容、Android heads-up 或 L1 深链；仅离线 migration reader 可读取 | dispatcher/inbox/receiver tests、Manifest、NotificationManager=0、migration audit |
| TD-79 | 唯一分析路由 | PC 断连、云 grant、解绑/重连、服务恢复和旧缓存重放下，同一 learner/session/generation 只有一个 route owner；PC 缓存绝不出域 | route lease ledger、ingress deny log、PC/cloud negative E2E |
| TD-80 | L0 心跳与停滞 | worker 卡死但 capture 持续时 watermark/worker lease 过期并转 `SEMANTIC_STALLED`；禁新 L1，连续达标恢复后才重开 | dual-clock trace、UI state、L1 negative/restore test |
| TD-81 | 连续上下文与预算 | 同 episode 下一连续 scope 可触达一次；gap/PTS/lineage/前台/归属任一失败或已达 episode 预算时仅 Discover | context relation audit、outbox、NotificationManager、dedupe test |
| TD-82 | 正式作答 fence scope | 只有显式 start receipt 建 learner-wide fence；另一 task/设备 close、Back/崩溃/断网不能解锁，同 assessment generation closure 才能 review | assessment/fence ledger、跨端 outbox、recovery test |
| TD-83 | 行为因果与独立性 | 同 episode 字符串但 session/source/consent 不同、UNKNOWN/AMBIGUOUS、PTS scope 外、过期、伪 adapter/attestation、重复 event/attestation、伪进度均不得确认兴趣；同一连续 lineage 的下一 scope 正例可通过策略窗口 | 行为账本、scope/PTS、adapter registry、attestation verifier、assessment decision trace |
| TD-84 | 本机 nonce 与锁屏披露 | PC snapshot 仍有效但 Android nonce/context/fence/revision 改变时不得 heads-up；默认锁屏不泄露概念/摘要/来源/行为/图谱，点击仍须 resolver；显式可见性只在授权设置内生效 | Android notification worker、NotificationManager、锁屏真机截图、Room/outbox/nonce audit |
| TD-85 | 音频语义充分、保真恢复与 late admission | 无轨/absence proof 单独不能标音频非必要；音频同步须有 clock domain、样本和策略上限。PC resume 的重复 ACK、乱序/缺序、PTS gap、hash/epoch 变化不得形成连续 scope；late fact 超时、重放、base revision/consent 不符 quarantine，不能推进 watermark 或二次通知 | Python 契约负例、fragment/outbox manifest、admission/revision ledger、Android/PC 后续集成验收 |
| TD-86 | LearningMoment 触达分责 | 长视频/直播同 episode 的多概念 anchor 形成独立 moment；scope/package/兴趣/图谱 revision 不得新建 moment 或普通通知；不同 episode 不因同概念合并。系统阻断、权限关闭、DEFERRED、graph patch 仍保留 Discover moment；已展示实质错误仅走限额 correction | moment/revision ledger、slot reservation、Room/outbox、graph reducer、NotificationManager、跨设备拒绝日志 |

## R-ID 覆盖映射

| R-ID | 必须通过的 TD |
|---|---|
| R01 | TD-01、TD-04、TD-12、TD-29 |
| R02 | TD-02、TD-13、TD-23、TD-24、TD-29 |
| R03 | TD-02、TD-29 |
| R04 | TD-03、TD-29、TD-85 |
| R05 | TD-02、TD-23、TD-29 |
| R06 | TD-06、TD-13、TD-29 |
| R07 | TD-07、TD-24 |
| R08 | TD-08、TD-16 |
| R09 | TD-09、TD-14 |
| R10 | TD-04、TD-12、TD-85 |
| R11 | TD-11、TD-15 |
| R12 | TD-27 |
| R13 | TD-28 |
| R14 | TD-05、TD-15、TD-21 |
| R15 | TD-29 |
| R16 | TD-13 |
| R17 | TD-15、TD-30 |
| R18 | TD-16 |
| R19 | TD-17 |
| R20 | TD-18 |
| R21 | TD-19 |
| R22 | TD-20 |
| R23 | TD-21 |
| R24 | TD-22 |
| R25 | TD-23 |
| R26 | TD-24 |
| R27 | TD-25 |
| R28 | TD-26 |
| R29 | TD-31 |
| R30 | TD-32 |
| R31 | TD-33 |
| R32 | TD-34 |
| R33 | TD-35 |
| R34 | TD-36 |
| R35 | TD-37 |
| R36 | TD-38 |
| R37 | TD-39 |
| R38 | TD-40 |
| R39 | TD-41 |
| R40 | TD-42 |
| R41 | TD-43 |
| R42 | TD-44 |
| R43 | TD-45 |
| R44 | TD-46 |
| R45 | TD-47 |
| R46 | TD-48 |
| R47 | TD-49 |
| R48 | TD-49 |
| R49 | TD-50 |
| R50 | TD-48 |
| R51 | TD-51 |
| R52 | TD-52 |
| R53 | TD-53 |
| R54 | TD-54 |
| R55 | TD-55 |
| R56 | TD-56 |
| R57 | TD-57 |
| R58 | TD-58 |
| R59 | TD-59 |
| R60 | TD-60 |
| R61 | TD-61 |
| R62 | TD-62 |
| R63 | TD-63 |
| R64 | TD-64 |
| R65 | TD-65 |
| R66 | TD-66 |
| R67 | TD-67 |
| R68 | TD-68 |
| R69 | TD-69 |
| R70 | TD-70 |
| R71 | TD-71 |
| R72 | TD-72 |
| R73 | TD-73 |
| R74 | TD-74 |
| R75 | TD-75 |
| R76 | TD-76 |
| R77 | TD-77 |
| R78 | TD-78 |
| R79 | TD-79 |
| R80 | TD-80 |
| R81 | TD-81 |
| R82 | TD-82 |
| R83 | TD-83 |
| R84 | TD-84 |
| R85 | TD-86 |

每个 TD 都要同时有失败测试和成功测试；真实验收不以 build、mock、截图或单项通知记录替代。

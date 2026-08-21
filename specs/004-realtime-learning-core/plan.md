# 重构实施计划与验收门

## 阶段 0：契约冻结与回归防线（P0）

1. 为本目录的数据模型和 v2 JSON 写 schema/契约测试。
2. 添加负向测试：音频关键语义缺口、静音但视觉文本完整、播放音频受限/失配、媒体明文/重放/跨 scope、episode 歧义、PC 断连、重复投递、关闭 visit 后简报到达、无云网关/网络零出域、通知权限关闭、迟到包、通知风暴、scope 失稳/修订、跨时钟误差超限、负反馈、风险内容介入、检索 SSRF/提示注入、图谱任务积压、正式作答 mode 栅栏、撤回 generation 竞态、系统 activity 污染、课程不适配、离线作答对账、通知 click/delete 并发和冷启动 deep link、PolicyBundle 签名/撤销/回滚、多设备 source/authority 竞争、证据链篡改、备份恢复删除、协议降级、L3 答案校验失败/撤销和迁移 quarantine。
3. 标记旧 candidate 生产链为 deprecated，禁止新功能引用。

**完成门**：测试能证明 L1 只由 `WINDOW_COMPLETE + CONTENT_ANALYSIS_PACKAGE.v2.l1 + InterestAssessment + LearningOfferAssessment=OFFERABLE + ContentSafetyAssessment=LEARNING_SAFE + 可验证音频/媒体安全/episode/scope` 开放，而不是由时长、current visit、TRIMODAL 候选、整段视频结束或 L2–L4 全量包开放。

## 阶段 1：PC 实时理解核心（P0）

1. 在现有 fragment ledger 上增加 `ContentEpisode`、`EpisodeBoundaryResolver` 与 `RealtimeSemanticFact`；不丢弃已封存片段，边界歧义只隔离为 L0。
2. 将画面/语音/文字并行 worker 输出改为 L0 增量事实与明确质量状态；建立 `AudioCapabilitySnapshot`、音频恢复队列、`L0SemanticHeartbeat`/`SEMANTIC_STALLED` 和每设备—模型 `RealtimeServiceLevelPolicy` 发布门。
3. 实现行为事件入站、兴趣评估、`LearningMoment + LearningMomentRevision`、嵌入 `ContentAnalysisPackage.v2` 的 L1 实时快照和增量修订；按证据范围和模型版本审计。媒体 episode 只管理连续性，moment 才管理概念锚点与普通 heads-up 去重；scope/package/兴趣/图谱修订不能重开普通触达。
4. 实现 PC `KnowledgeEnrichmentAgent`：以 L1 概念锚点受控联网检索，生成带来源/冲突状态的 `CONTENT_GRAPH_REVISION.v2`；置于不抢占 L0 的低优先级队列，不得参与 L1 资格或兴趣判断。
5. 为 FastAPI gateway 加入 v2 outbox 与 ACK/NACK，并为媒体 data plane 实施会话加密、双向认证、MAC 与防重放；实现 `AnalysisRouteLease`、签名 PolicyBundle/PolicyTrustRoot、协议兼容验证、证据完整性/检查点、可信时间、多设备 lease/authority；旧 candidate 链只读且不再拥有 Android broadcast/通知入口。

**完成门**：已批准配置的真实连续媒体下能显示 L0 进展、音频/边界/媒体安全质量及 SLO；稳定、非歧义窗口与兴趣事实能在内容未结束时形成可重投的 L1 简报，后续内容以同一 episode 增量补齐。

## 阶段 2：Android 领域、数据库与 transport（P0）

1. 创建纯 Kotlin `core:model`，先以 TDD 实现 episode、兴趣门、学习路径与包验证。
2. 引入 Room；实现 package 原子事务、`LearningMoment` create-or-hit 与 revision DAG、每 episode slot reservation、receipt、notification outbox/attempt lease、InterruptionPolicy/QuestionValidation/CurriculumAlignment 表、scope 复合键/FK、consent fence、媒体安全/音频/边界/安全评估表与旧图谱迁移桥。
3. 在不改 MediaProjection/RTSP 真入口的前提下，实现 `AnalysisTransport`、PC v2 适配和本地缓存续传。
4. 实现 `CloudAnalysisTransport` 的 disabled/unavailable 状态和契约测试；在 `CloudDataPolicy` 冻结、团队网关可用及真机验收以前，不接入任何云执行或供应商聊天 key。无 PC 正式发布门必须另行完成团队网关真链，不能把 unavailable 当作最终产品能力。

**完成门**：PC 包在 Android 落库成功才 ACK；PC 断连只缓存；无 PC 且无网关时明确不可用。

## 阶段 3：V5 UI 行为重构（P0）

1. 抽取 V5 tokens、Panel、按钮、分段控件、图谱画布至 design system，视觉不改版。
2. 接入 Navigation Compose，路由替换为 `l1/{briefId}`；`packageId + packageRevisionId` 只用于加载内容版本；`BriefAccessResolver` 处理撤回/过期/隔离/未就绪，深链、系统 Back、进程恢复均有测试。
3. 按 feature 拆分 ViewModel：capture、discover、L1、knowledge、practice、profile、connection。
4. 用真实 Room Flow 代替 QA fixture、SharedPreferences 候选状态和 composable 内 service locator 调用。
5. 正式 L2 只渲染 `ContentGraphRevision` 与学生 patch 覆盖层；将硬编码 `ContentConceptCanvas` 降为 debug fixture，并切断 `KnowledgeGraphProjector` 自动写入长期画像的路径。
6. L3 实作可核对且答案已校验的客观题，L4 实作主观论证与回执；保留 L2 图谱的学生修订。

**完成门**：Android heads-up 点击进入正确 L1 包；所有可见按钮有真实状态/目标；不以样例或 Toast 冒充行为完成。

## 阶段 4：真实验收与迁移删除（P0）

1. 在真机 MediaProjection 持续公开媒体上记录媒体 PTS、入站、语义、兴趣、包投递、heads-up 与点击的全链日志。
2. 验收自然结束、倍速有效覆盖、图文读完、直播语义窗口、音频失败、PC 断连恢复和重复投递。
3. 对眼镜单独完成 capture adapter/时间同步/许可验收后才并入同一链；未接入前只标注待实现。
4. 部署团队云网关后，以 Android 无 PC 模式完成授权、L0、L1、撤回删除同次真机验收；验收同时覆盖 PolicyBundle、完整性链、备份 manifest 和协议兼容；未通过前不能发布为无 PC 可用。
5. v2 正向链通过后，按 `migration.md` 迁移旧图谱和必要用户数据，先交付计数/hash/quarantine/导出与只读回退报告，再删除旧 candidate/visit 通知运行入口。

**完成门**：在通知权限、频道、锁屏和 DND 已配置的指定基准真机上，一次连续真机操作中可见并点击正确的 L1 heads-up；其他设备至少证明包持久化、NotificationManager 提交与正确深链。报告不将 mock、构建或离线回放当作闭环。

## 实施顺序约束

- 先契约与领域测试，再服务端/Android 适配，最后页面接线；不得反向从 UI 推导业务规则。
- 按 `capability-profiles.md` 分档实施和验收。`DOMAIN_UI_INTEGRATION` 允许在真实 Room、真实 unavailable/撤回状态下先接 UI；它不允许 fixture、CandidateCard 或虚构 L1。真正的 L1 通知只由 `LOCAL_PC_L1` 档打开。
- T001–T006、T012–T017、T035–T040、T049–T055、T059–T060、T062–T063、T098–T099 是 `DOMAIN_UI_INTEGRATION` 的硬门。云、眼镜、正式作答、备份、竞赛和跨设备增强各自按档位门控，不能反向阻塞本地 PC 核心，也不能借本地成功跨档位声明。
- PC 本地链完成并真实验收前，不开通云端生产路径；T032 只在 CloudDataPolicy、团队网关和独立真机链均齐备时执行，未具备时长期保持 unavailable。
- 面向无 PC 用户的产品发布必须完成 T056 的真实云端闭环；`UNAVAILABLE` 只是安全降级，不能作为该用户路径的验收完成。
- 任何删除只发生在 T030、T034–T041 的适用迁移/安全/质量门及真实回归都通过之后。眼镜、云端、纸笔教材等未通过其专属任务时必须保留“未接入/未完成”状态，不能随手机 PC 链一起宣称完成。

### 不可绕过的依赖门

| 门 | 必须先完成的任务 | 被保护的后续路径 | 未完成时唯一允许状态 |
|---|---|---|---|
| G1 语义与可复现 | T001–T007、T041、T049、T072、T073、T075、T080、T084–T085、T092、T095、T097 | PC L0/L1、图谱与竞赛结论 | L0 质量记录或 `NOT_REALTIME/SEMANTIC_STALLED`，无 L1 |
| G2 L1 触达 | G1 + T008、T015–T016、T031、T062、T074、T076、T083、T088、T090、T093、T096、T099 | Android heads-up | Discover/unavailable；不得提交高优先级通知 |
| G3 学生控制 | T021、T031、T060、T077、T082、T086 | L2、长期索引、助手操作 | 只读/建议；无自动长期写入或自动操作 |
| G4 敏感/云/导出 | T024、T032、T042–T043、T053–T057、T078、T080、T087 | 云端、敏感处理、导出、竞赛声明 | capability `UNAVAILABLE`，零出域 |
| G5 正式作答 | T045、T058、T061、T081、T094 | L3/L4 与交卷后复盘 | 只记录或 unavailable，fence 保持 |
| G6 v2 切换/删除 | G1–G5 的适用子集 + T017、T030、T067、T079、T090–T091 | 旧链删除、v2 发布 | legacy 只读，不恢复 candidate 通知 |

任务可并行编写失败测试，但不得在所属门未通过时接通受保护的生产副作用。任何临时调试路径、fixture、shadow 或回退都必须保持该表的拒绝语义。

## UI 无障碍验收基线

Compose + Material 3 不自动构成无障碍完成。连接开始/停止、L1 深链、证据抽屉、打扰/长期索引撤销、正式作答 fence 与通知 action 均须具备 `Semantics`、TalkBack 文案、动态字体不截断、最小触控目标、确定焦点顺序和非颜色唯一状态。任何关键学生路径未通过语义树、自动扫描及基准真机手工路径时，不得以截图或视觉一致性宣布 UI 可用。

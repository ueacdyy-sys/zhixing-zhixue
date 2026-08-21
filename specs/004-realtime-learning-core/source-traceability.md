# 权威材料—冻结规格追溯

本表以 `C:\Users\Administrator\Desktop\华为杯\可行性材料\大赛可行性方案.docx` 和 `知行智学：项目汇报.pptx` 为来源。若材料的早期表述与用户 2026-07-29 最终校正冲突，后者优先；本表明确保留来源意图而不让旧口径回流到实现。

| 权威来源 | 原始意图 | 冻结落点 | 验收 R-ID | 冲突/处理 |
|---|---|---|---|---|
| 方案 P11–21，P44，P108；PPT 6/8 | 多设备、兴趣—学习承接—过程复盘、PC 本地中枢与可解释证据 | `ContentEpisode`、统一时间轴、EvidenceCard、PC/纸笔独立入口 | R01、R07、R08、R19、R30 | 保留，不把采集直接推导为结论 |
| 方案 P17–18、P25–27、P49；PPT 9–11；用户最终校正 | 日常兴趣、低打扰提示、自愿分层探索；前段概念可先触达、图谱后续生长 | L0–L4、L1 scope+兴趣门、`LearningMoment`、`InterruptionPolicy`、L2 图谱、L3/L4 | R02、R03、R06、R07、R09、R16、R85 | 旧“悬浮窗/四层”叙述服从最终 Android 系统 heads-up + L1 页面定义；scope/图谱修订不重开普通通知 |
| 方案 P14–15、P29、P100–106；PPT 4–5、12–13 | 纸笔/教材的过程记录、交卷后复盘、人工复核 | `AssessmentSession`、`POST_ASSESSMENT_REVIEW`、EvidenceCard | R19、R29、R30 | 正式作答期间只记录、零干预；不以单一状态流推断能力 |
| 方案 P35、P56–58、P62–63；PPT 6、15–16、18 | 眼镜/EEG/手表为增强证据，按时间轴融合并可降级 | `StateSignalWindow`、时钟不确定度/伪迹门、眼镜 source adapter | R12、R31 | 未真实接入前必须标未完成；状态流仅质量/趋势线索 |
| 方案 P61、P71–72、P119–138；PPT 15、18–19；用户最终校正 | 连续媒体主链、API/本地演进、关键帧仅性能控制、真实正向证据链 | L0 facts/scope、RealtimeServiceLevelPolicy、AudioCapabilitySnapshot、MediaSecuritySession、PC local/团队 cloud、真实 E2E 包 | R01、R04、R10、R11、R15、R26、R34–R38 | 最终用户约束优先：配对 PC 只走本地，断连只缓存；云未部署则 unavailable，且 unavailable 不是无 PC 用户交付 |
| 方案 P65–68、P101；PPT 9、13、15 | 受控语文资源、知识映射、掌握趋势、证据卡 | `CurriculumResource`、EvidenceCard、L3 QuestionValidation、PersonalEvidenceIndex | R08、R09、R30 | 掌握趋势需题目/作答等主证据；不得成为人格/医学/确定性专注诊断 |
| 方案 P87–94；PPT 17、19–20；适用安全/合规审查 | 会话授权、最小必要采集、本地优先、脱敏/删除审计 | CapturePolicy、Consent/Retention/Deletion、CloudDataPolicy、ContentSafetyAssessment、scope 隔离、检索沙箱、ControlledEvidenceExport | R14、R17、R20、R21、R23、R27、R28、R32、R39–R41 | 未知/敏感画面编码前阻断并删除；不建浏览史或生理监控后台；缺适用授权或安全门时不外发、不介入 |
| 方案 P77–79、P105–106；PPT 18 | 单设备→组合→算法优化的验证顺序、质量与降级 | TD-01–TD-34、分阶段任务与 SLO/质量门 | R12、R15、R26、R31 | 不以构建/截图/单设备展示替代组合证据 |
| 《需求》表 4、表 9、表 10；P52–55、P94 | 量化验收、消融、错误案例与“已实测/待验证/禁止声称”边界 | `CompetitionValidationProfile.v1`、能力声明等级 | R15、R26、R33 | 数值是实验门，不是对学生的产品评分阈值 |

## 明确不继承的旧表述

1. PPT 对“注意力/疲劳度量化、能力表现、教师管理端”的宽泛叙述，不能突破最终冻结的非诊断、无当前教师登录/UI、受控导出边界。
2. 旧方案的“API 优先”不能覆盖“配对 PC 优先、PC 断连不自动切云”；云端仅在独立 policy、认证、预算、删除和真机验收齐备后启用。
3. 旧候选卡、TRIMODAL、新鲜度、visit 打开状态与一次停留，不是 L1 或学习分级门。

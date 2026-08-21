# 旧链迁移、隔离与删除门

## 1. 迁移原则

迁移不是把旧数据自动升级为 L1。旧 `CandidateCard`、visit、新鲜度、TRIMODAL 和历史候选只能作为只读证据源；它们绝不获得 `L1_ELIGIBLE`、系统通知或 L2–L4 资格。旧数据无法无损映射时进入 quarantine，不丢弃、不伪造。

## 2. 映射表

| 旧数据/入口 | 目标 | 允许迁移 | 必须隔离 |
|---|---|---|---|
| `candidate_card.v1` / `PcKnowledgeAnalysisResult` | `legacy_migration_records` + 可选 L0 历史证据 | 仅保存来源、哈希、时间、设备、可解析证据 locator | 不生成 `L1LearningBrief`、不发通知 |
| 旧 PTS/片段/哈希账本 | `capture_sessions`、`ContentEpisode`、`L0FactBatch` | 有连续性与许可依据时迁入原始事实/媒体定位 | 边界不确定、缺许可或坏哈希的记录 quarantine |
| 手写 SQLite 图谱与编辑事件 | `StudentGraphPatch` | 迁移学生显式改名、笔记、加/删边、隐藏、纠错，并保留原源 ID | AI 自动关联与 `profile_entries` 不迁入长期画像 |
| SharedPreferences 候选/学习路径 JSON | 只读导出或 `legacy_migration_records` | 可解析且与用户主动编辑有关的 UI 偏好 | 业务状态、自动推荐与旧通知字段不写入 Room 新链 |
| `candidate_notice_dispatcher.py`、旧 codec/旧 JSON 写入 | 无 | 不迁移运行行为 | 仅在删除门通过后删除入口 |

## 3. 迁移执行与回退

1. 先导出不可变清单：源路径、记录数、每类 SHA-256/内容哈希、解析错误与许可证/同意状态。
2. 迁移器以 `learnerId + sourceSystem + sourceId + sourceHash` 幂等写入 `legacy_migration_records`，逐条记录目标 ID、结果、quarantine 理由和时间。无法确定学生归属的历史记录只能 quarantine，不能默认并入当前设备用户。
3. 新旧并行期，旧存储只读、旧生产入口不得接收新写入；回退只允许切回旧只读展示或从导出重跑迁移，绝不从新链反向写回旧 JSON。
4. 数据损坏、缺引用、重复 hash、无许可、无法归属或 schema 不兼容必须 quarantine，并能由用户导出查看。

## 3.1 受控切换与回退

1. `CutoverReleaseGate` 初始为 `LEGACY_READ_ONLY`。只有 v2 领域、Room 原子包、拒绝门和对应 TDD 通过后，才可对同一 learner/device 进入 `V2_SHADOW_L0`。
2. 影子运行只复用当前会话已经获许可的 evidence locator，产出可审计 L0 对照；不得二次采集/保存原始媒体，不得建立 L1、通知、长期画像、图谱自动写入或影响学生策略。
3. 影子样本的事实一致性、拒绝门、资源/SLO 与删除 fence 通过后，才可由签名策略将该 scope 进入 `V2_ACTIVE`。启用范围、版本、证据和操作者必须写 receipt。
4. 故障回退只能转为 `V2_DELIVERY_DISABLED`：停止 v2 新投递并保留其证据/删除语义，旧链维持只读迁移展示。不得为了恢复通知重新启用 `candidate_notice_dispatcher.py`、旧 visit 规则或旧 JSON 写入。

## 4. 旧入口删除门

只有下列条件全部满足，才允许删除旧 candidate/visit 通知运行入口和旧 JSON 业务写入：

1. v2 映射计数、成功/失败/quarantine 计数和 hash 抽样回读均通过；
2. 迁移后的学生 patch 能在 `ContentGraphRevision + StudentGraphPatch` 覆盖层回放；
3. 真机真实媒体的 L0→L1、通知深链、撤回删除、PC 断连恢复和 Android 进程恢复回归全部通过；
4. 已提供用户数据导出，迁移报告和至少一个只读回退期；
5. 删除清单精确到文件/运行入口，并由独立测试证明新链没有任何生产依赖。

未满足时只冻结旧写入和隔离旧入口，不能以目录名、代码引用数或构建通过为由删除。

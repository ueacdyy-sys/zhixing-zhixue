# 数据模型与可追溯关系

`Session 1—N Task 1—N Phase`；`Device` 通过 `DeviceConnection` 加入 Session；每个 `Capture` 与 `Event` 归属一个 Session；`Evidence` 引用一个或多个 Event/Capture 时间窗口；`Window` 聚合 Evidence；`EvidenceCard` 引用 Window；`LearningStep` 与 `ExportPackage` 均可追溯到 Session。

| 实体 | 必要字段 | 关键规则 |
|---|---|---|
| Session | session_id, user_hash, consent_scope, status | 必须可暂停、关闭 |
| Device | device_id, device_type, capabilities, owner_scope | 手机、PC、眼镜、可穿戴设备均以适配器能力接入 |
| DeviceConnection | connection_id, device_id, transport, status, clock_offset_ms, quality | 手机负责发现、授权与会话控制；高带宽数据可直连 PC 本地中枢 |
| Task | task_id, session_id, task_type, goal, knowledge_tags | 可由 PC、纸笔或手机自愿探索产生 |
| Capture | capture_id, source, modality, start/end_ts, quality | 原始证据与摘要分层 |
| Event | event_id, task_id, event_type, start/end_ts, confidence | 保留原始与校准时间 |
| Evidence | evidence_uri, event_ids, capture_range, privacy_level | 必须可回放或明确缺口 |
| Window | window_id, type, evidence_ids, score, uncertainty | 不等同能力/专注度标签 |
| EvidenceCard | facts, interpretation, counterevidence, action, review_status, downgrade_reason | 解释必须引用 Evidence |
| ExportPackage | export_id, session_id, event_refs, card_refs, quality_refs, created_at | 为未来教师端/人工复核保留结构化读取入口，不包含教师 UI 状态 |

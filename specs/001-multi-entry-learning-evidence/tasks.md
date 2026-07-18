# Tasks: 多入口学习过程证据平台

## Phase 1 — Setup

- [x] T001 固化 `services/local-hub/src/zhixingzhixue_hub/contracts/event.schema.json` 与 `evidence-card.schema.json`，对应 `contracts/event-and-card-contract.md`
- [x] T002 建立 `tests/contract/`，配置本地无网络测试命令

## Phase 2 — Foundational

- [x] T003 先写失败契约测试 `tests/contract/test_event_required_fields.py`，覆盖 session、来源、时间、质量与证据 URI
- [x] T004 在 T003 失败后实现 `src/core/event_validator.py` 的最小验证逻辑
- [x] T005 先写失败测试 `tests/device/test_connection_contract.py`，覆盖设备身份、传输方式、会话、时钟偏差、能力与连接状态
- [x] T006 在 T005 失败后实现 `src/devices/connection_contract.py`，保持手机/PC/眼镜/可穿戴适配器可替换

## Phase 3 — 手机日常兴趣 MVP [US1]

- [x] T006A [US1] 先写失败测试 `tests/phone/test_keyframe_ocr_candidate.py`，验证关键帧 OCR 仅能输出带帧引用的 `CANDIDATE_ONLY`，不得输出学习诊断或兴趣结论
- [x] T006B [US1] 实现 `src/zhixingzhixue_hub/phone/keyframe_ocr_candidate.py` 的手机屏幕流降级候选门控
- [x] T007 [US1] 先写失败测试 `tests/phone/test_full_segment_required.py`，验证缺少完整视频或同源音频时不得产生兴趣结论
- [x] T008 [US1] 实现 `src/phone/interest_session.py` 与 `src/analysis/slow_path.py` 的完整片段任务封装
- [x] T009 [US1] 先写失败测试 `tests/phone/test_single_dwell_no_practice.py`，验证单次停留不生成练习且可记录关闭/稍后回执
- [x] T010 [US1] 实现 `src/learning/l0_l4_gate.py`、`src/evidence/card_builder.py` 与手机回执写回

## Phase 4 — PC 实践与分析中控台 [US2]

- [x] T011 [US2] 先写失败测试 `tests/pc/test_task_session.py`，验证 PC 任务可独立创建而不依赖手机会话
- [x] T012 [US2] 实现 `src/pc/task_workbench.py` 的任务、阶段、学习行为采集和手机证据卡查看
- [x] T013 [US2] 先写失败测试 `tests/timeline/test_pc_timeline.py`，验证网课/检索/写作事件可回放
- [x] T014 [US2] 实现 `src/timeline/aligner.py` 与 `src/analysis/fast_path.py` 的事件对齐和候选权限隔离

## Phase 5 — 增强证据与导出预留 [US3][US4]

- [x] T015 [P] [US3] 先写失败测试 `tests/quality/test_low_quality_exclusion.py`
- [x] T016 [US3] 实现 `src/quality/modality_gate.py` 与降级日志
- [x] T017 [P] [US4] 先写失败测试 `tests/export/test_evidence_export.py`，验证结构化导出包含证据、质量与降级信息但不依赖教师 UI
- [x] T018 [US4] 实现 `src/export/evidence_package.py` 的导出包构建；教师端认证、界面、批注和复核延后

## Phase 6 — Validation

- [ ] T019 执行两条真实正向链的端到端测试并保存 `evidence/validation/` 脱敏日志（当前仅完成确定性领域编排链；待接入真实受控样本/采集适配器后验收）
- [ ] T020 运行指标、消融、删除和引用合规检查，更新 `docs/tdd/test-matrix.md`

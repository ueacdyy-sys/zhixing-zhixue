# 完整视频正向学习闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. All behavior changes use TDD.

**Goal:** 让真实手机 canonical 视频完成完整视频理解、证据卡、兴趣微任务和可回放界面。

**Architecture:** 快路径继续负责候选分段；语义慢路径直接读取完整 canonical 视频和同源音频。高质量 ASR 与视频模型结果通过 capture_id、媒体摘要和时间范围融合，最后由本地 Web 页面呈现。

**Tech Stack:** Python 3.11、PyTorch CUDA、Qwen2.5-VL、faster-whisper、FastAPI/静态 Web。

---

### Task 1: 本地模型运行时

**Files:**
- Modify: `requirements-full-video.txt`
- Create: `scripts/full_video_runtime_check.py`
- Test: `tests/test_full_video_runtime_check.py`

- [ ] 先写模型、CUDA、视频解码和显存检查的失败测试。
- [ ] 安装并验证 PyTorch CUDA、Transformers、Qwen VL 工具和视频解码依赖。
- [ ] 下载并验证 3B 视频模型和 large-v3-turbo ASR 模型。

### Task 2: 完整视频理解探针

**Files:**
- Create: `scripts/full_video_understanding_probe.py`
- Test: `tests/test_full_video_understanding_probe.py`

- [ ] 先写拒绝图片列表/抽样帧主输入、要求完整视频路径的测试。
- [ ] 校验 canonical report、capture_id、SHA-256、音视频轨和持续时间。
- [ ] 运行高质量 ASR，保留时间戳和质量。
- [ ] 将完整视频文件与 ASR 时间文本送入视频模型，要求严格 JSON。
- [ ] 输出事件、概念、时间证据、不确定性和模型处理披露。

### Task 3: 证据卡与兴趣微任务

**Files:**
- Create: `scripts/learning_evidence_builder.py`
- Test: `tests/test_learning_evidence_builder.py`

- [ ] 先写证据卡必须引用真实时间范围和媒体摘要的测试。
- [ ] 拒绝只有 OCR、单帧或无时间范围的语义。
- [ ] 生成解释、延伸、保存、稍后看或复盘型微任务，禁止题目推荐。
- [ ] 输出 `evidence_cards.json` 和 `microtasks.json`。

### Task 4: 可回放演示界面

**Files:**
- Create: `demo_app/server.py`
- Create: `demo_app/static/index.html`
- Create: `demo_app/static/app.js`
- Create: `demo_app/static/styles.css`
- Test: `tests/test_demo_app.py`

- [ ] 先写数据加载、视频路径、时间跳转和状态显示测试。
- [ ] 实现原视频播放器、时间线、证据卡和微任务面板。
- [ ] 点击证据跳转到原视频对应时间。
- [ ] 明确显示已实测、推断和未验证。

### Task 5: 真实 B 站端到端验收

**Files:**
- Create: `captures/<run>/full_video_understanding_report.json`
- Create: `captures/<run>/evidence_cards.json`
- Create: `captures/<run>/microtasks.json`
- Create: `captures/<run>/demo_validation.json`

- [ ] 使用真实 canonical 视频运行完整语义链。
- [ ] 人工回放核验事件、概念和微任务与原视频一致。
- [ ] 启动页面并验证证据时间跳转。
- [ ] 全量测试、py_compile 和最终产物检查。


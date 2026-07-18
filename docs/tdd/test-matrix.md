# TDD 测试矩阵

| 行为 | Red：先失败测试 | Green：最小实现 | 必须回归 |
|---|---|---|---|
| 手机完整证据与自愿回执 | 缺连续媒体/同源音频，或单帧候选请求练习时必须失败 | 完整片段门控、卡片与保存/稍后/关闭回执 | 完整片段可回放；不强迫迁移 PC |
| PC 独立学习入口 | 无手机会话仍能创建 Task；跨任务/跨阶段事件必须失败 | PC Task、Phase、事实行为记录 | 网课定位、检索、写作可按时间回放 |
| 快路径隔离 | 候选请求卡片、解释、练习或测验必须失败 | 仅输出候选 ID、事件引用和本地证据引用 | 无知识结论、诊断、卡片或学习干预字段 |
| 证据卡与质量降级 | 不完整事实或未完成慢路径的卡必须失败 | 事实/解释/反证/不确定性分离；质量降级 | 低质量时解释清空、置信度降为 low |
| 低质量模态 | 遮挡、断连、伪迹、时间残差超限不得融合 | FUSION_ELIGIBLE / RECORD_ONLY / EXCLUDED 与质量日志 | 可穿戴只作趋势/质量辅助，无医学或能力结论 |
| 结构化导出预留 | 跨会话、重复 ID、非 local URI、无时区时间必须失败 | 版本化 ExportPackage、事件/卡片/质量引用 | 无教师 UI、登录、凭证、批注或复核流程 |
| 端到端与脱敏日志 | 两条正向链必须通过且日志含敏感键/外部 URI 时失败 | 确定性领域链验证、脱敏 JSON、引用合规检查 | 当前为 60 项领域编排测试与 2 份脱敏日志；真实采集样本链待接入 |

## 当前验证证据

- 单元与集成测试：`services/local-hub/.venv/Scripts/python.exe -m pytest`，60 项通过。
- 静态检查：`ruff check src tests` 通过；`compileall -q src scripts` 通过。
- 两条领域编排链日志：`services/local-hub/evidence/validation/phone-public-media-chain.json`、`pc-learning-chain.json`。日志只保留不可逆引用指纹，不含原始本地 URI。
- 引用与脱敏检查：`scripts/verify_validation_artifacts.py`。验证日志不含教师字段、凭证、用户哈希、令牌、ADB 标识、`local://` 或外部 URI。
- 历史虚拟环境尝试保留在 `services/local-hub/_previous-attempts/`，不属于最终运行时；当前有效环境是 `services/local-hub/.venv/`。未删除用户保留的历史尝试。

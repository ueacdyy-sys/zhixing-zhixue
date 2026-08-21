# 无 PC 云端分析数据边界

## 1. 默认关闭与启用门

`CloudAnalysisTransport` 默认 `DISABLED`。在以下清单全部以版本化 `CloudDataPolicy` 冻结并且团队自有网关可连通前，Android 不得对任何公网主机发送媒体、转写、行为、图谱、个人索引或供应商模型凭证：

1. 显式、可撤回的云分析 `ConsentReceipt`；
2. 显式认证的 cloud `LearnerScope`，不得用 Android deviceId、PC pairing token 或 IP 地址代替账号归属；
3. 逐数据类别 allowlist 与最小化规则；
4. 受控 HTTPS 网关地址、证书 pin/短期设备认证及服务身份；
5. 数据区域、保留期、配额/成本上限和速率限制；
6. 服务端删除级联、可查询 `DeletionReceipt` 与失败重试；
7. Android 真机从授权到 L0/L1、撤回删除的完整验收。

缺少任一项时 capability 只能返回 `UNAVAILABLE`，Android 显示 `CAPTURE_PENDING_ANALYSIS`；不得把采集缓存、聊天 API 或模拟包称为云端理解。

手机直连聊天 API 与本契约隔离：其输入只能是学生显式输入的文本和单独选择的附件，默认没有 `captureSessionId`、`learnerId` 内容 scope、媒体、转写、行为、图谱或画像访问权限。它不能被 `AnalysisTransport`、PC 断连恢复、L0 worker 或通知任务调用。

## 2. 已启用策略最小结构

```json
{
  "policyVersion": "...",
  "learnerId": "cloud-authenticated-subject-derived",
  "region": "...",
  "allowedData": ["MEDIA_FRAGMENT", "BEHAVIOR_EVENT"],
  "forbiddenData": ["RAW_FULL_SESSION", "PERSONAL_EVIDENCE_INDEX", "MODEL_PROVIDER_KEY"],
  "retention": {"MEDIA_FRAGMENT": "...", "DERIVED_FACT": "...", "AUDIT_RECEIPT": "..."},
  "quota": {"perDevice": "...", "perUser": "...", "failAction": "STOP_AND_REPORT"},
  "auth": {"deviceCredential": "short-lived", "serviceIdentity": "pinned"},
  "deletionSlo": "policy-owned"
}
```

传输前由 Android 和网关双重验证 consent、allowlist、来源许可、大小/配额和 session 绑定。网关只能使用团队配置的服务器端模型凭证；APK、日志、通知和故障回显不得出现供应商密钥或原始媒体内容。

## 3. 生命周期与审计

- 每个上传对象带 `learnerId`、`captureSessionId`、`episodeId?`、内容哈希、时钟范围、policyVersion、consentId 和可关联的删除根。网关必须同时校验 token、设备凭据与 learner scope 的绑定；跨 scope 读取、ACK、evidence resolver、删除或图谱 patch 一律拒绝。
- 网关拒绝未知字段、未授权来源、过期 token、跨区域对象与未允许的数据类型；拒绝不会降级为第三方直连。
- 撤回时 Android、云网关、对象存储、任务队列、向量/检索索引、内容包与通知 outbox 都生成同一删除链的 receipt。任何一端未确认前状态为 `DELETE_PENDING`，且禁止再分析、投递、联网补全或展示原内容。
- 云端只替换计算与存储部署，消息、证据定位、权限和删除语义必须与 PC 本地 transport 同构。

# 真实验收运行指南

## 前提

1. 使用真实 Android 设备，学生主动授予 MediaProjection 与通知权限。
2. 已配对 PC 的本地 gateway、模型、媒体 worker 和 HTTPS/SPKI pin 均处于可用状态。
3. 媒体 data plane 已建立 `MediaSecuritySession`，并能证明双方身份、加密、分片 MAC 和 anti-replay 状态；不以“同一局域网”代替该前提。
4. 验收媒体为允许采集的公开内容；不使用离线文件、mock 事件或 QA fixture 代替持续流。
4. Android 构建统一从 `C:\ZhixingZhixue` Junction 进入，避免中文路径 Gradle 偶发问题。

## 必测场景

| 场景 | 期望事实 |
|---|---|
| 视频中途形成兴趣 | L0 连续事实 → `STABLE` scope → L1 brief/heads-up；视频未结束时已可打开 L1 |
| 音频关键缺口 | 记录 `AUDIO_REQUIRED_UNRESOLVED`，无 L1；修复后以新修订继续 |
| 音频能力受限 | `AudioCapabilitySnapshot` 清楚标明播放/麦克风/混音、系统/应用限制和同步误差；不得以环境音或“无声”绕过 |
| 无声视觉内容 | 只有审计证明音频非必要时可按完整语义继续，不得由采集失败冒充 |
| 图文/直播 | 图文主要内容读完或直播语义窗口闭合后按相同门控；纯带货不生成知识结论 |
| PC 断连 | 手机缓存/传输 outbox 持续；恢复后同 episode 续传，无云切换、无静默丢失 |
| 通知受阻 | 包持久化并 ACK，发现页可见；记录 blocked/suppressed，不说 heads-up 已送达 |
| 图谱生长 | L1 概念锚点存在；联网 revision 有来源/冲突状态；L0 新事实更新同一 content graph |
| 长期索引 | 未保存/确认/练习/复盘的内容图谱不出现于长期知识全览 |
| 打扰策略 | 系统阻断、dismiss、稍后、主题屏蔽、撤销各自有正确策略状态；系统阻断不等于不感兴趣 |
| L3 校验 | 不存在同一生成器自证的题目；依据撤销后题目下架，历史作答保留审计 |
| 迁移 | 旧记录有计数/hash/quarantine/导出与只读回退报告；旧 candidate 不变成 L1 |
| 云数据边界 | policy disabled 时抓包显示零出域；正式启用后只出现 allowlist 内的会话数据和删除 receipt |
| 媒体安全 | 明文、过期、MAC 错误、重放、跨 learner 分片与可猜测 endpoint 均被拒绝；无密钥/原始媒体泄露到日志 |
| 内容边界 | 分屏、浮窗、广告、评论区、切换和 PTS epoch 重置进入可解释新 episode 或 `EPISODE_AMBIGUOUS`；后者无 L1/图谱合并 |
| 强制 scope | 共享 PC/换机/缓存恢复下跨 learner ACK、深链、patch、导出、删除全部失败关闭；仅显式 transfer 可迁移 |
| 检索沙箱 | 私网/metadata/DNS 重绑定/恶意重定向/提示注入/压缩附件不能触达内部资源，也不改变 L0/L1 |
| 无 PC 云链 | 仅在真实团队网关上，以 Android 真机完成授权→L0→L1→撤回删除；否则保持 `UNAVAILABLE` |

## 必收集证据

- PTS、媒体哈希、到达/封存/语义/brief/通知/点击时间线；
- worker 队列深度、输入与处理速率、p50/p95/max 延迟和降级原因；
- 设备—模型批准 SLO、AudioCapabilitySnapshot、episode boundary ledger、媒体安全会话/分片拒绝日志和 learner scope 授权拒绝日志；
- Android 包持久化 receipt、PC ACK/NACK、通知 outbox 状态；
- L2 来源抽屉、revision 链和学生 patch 事件；
- 对每个场景的失败证据，不以构建、单测、`dumpsys notification` 或截图单独替代真实闭环。
- 对云端未配置、眼镜未接入或迁移未过删除门的能力，验收报告必须明确标为未完成，不能由接口、页面、mock 或网络可达性替代。

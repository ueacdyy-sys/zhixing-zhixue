# L1 打扰策略与负反馈契约

`InterruptionPolicy` 只决定 L1 的触达方式，不能修改 `InterestAssessment`、`LearningOfferAssessment`、L1 内容或历史证据。任何决策先持久化 brief，再决定 heads-up、延后或仅发现页。

## 1. 版本化策略快照

每次决策必须持久化下列不可变快照，而不是读取会被后来配置覆盖的全局偏好：

```json
{
  "policyId": "interruption-policy-...",
  "version": "...",
  "timezone": "Asia/Shanghai",
  "quietHours": [{"start": "22:30", "end": "07:30"}],
  "frequencyBudget": {"episode": 1, "topicWindow": "PT24H", "topicMax": 1},
  "topicSimilarity": {"method": "versioned-embedding", "threshold": "policy-owned"},
  "defer": {"maxAge": "PT30M", "retryOnlyWhileRelevant": true},
  "secondNotice": {"requiresStudentEnteredL1OrExplicitSubscription": true},
  "correction": {"maxPerBriefRevisionChain": 1}
}
```

具体阈值只允许出现在经样本校准的策略版本中；代码、UI 文案和模型 prompt 均不得私自写死。

## 2. 决策与过期

- `NOTIFY_NOW`：当前 Android 能力允许、用户处于相关内容上下文、未耗尽预算且不在安静时段时，创建一条 heads-up 尝试。
- `DEFERRED`：brief 已进入发现页，保存 `deferUntil` 与失效时间。到期后仅在内容仍相关、许可有效且预算允许时再次评估；过期后转为 `SUPPRESS_HEADS_UP_KEEP_IN_DISCOVER`，不得补发陈旧高优先级通知。
- `SUPPRESS_HEADS_UP_KEEP_IN_DISCOVER`：内容保留、可打开、可学习，但不创建高优先级通知。
- `CORRECTION_NOTIFY`：仅当先前已呈现的解释被实质修正、学生尚未撤回许可、且本 revision 链未用完一次更正额度时可用；更正必须说明版本变化，不能静默替换历史。

系统权限、OEM、DND、网络或通知频道导致的阻断只能写 `NotificationStatus=BLOCKED_*`，绝不转写为“不感兴趣”。

## 3. 反馈事件语义

| 事件 | 是否负反馈 | 默认作用域 | 是否可撤销 |
|---|---:|---|---:|
| `SYSTEM_BLOCKED` | 否 | 单次通知技术状态 | 否 |
| `DISMISSED` | 否；仅可作为版本化重复模式的弱信号 | 单次 brief | 否 |
| `DEFER_BY_USER` | 否 | 单次 brief，到期后重评 | 是 |
| `NOT_INTERESTED` | 是 | 明示主题/概念或 brief | 是 |
| `TOPIC_MUTED` | 是 | 主题相似度簇 | 是 |
| `QUIET_HOURS_CHANGED` | 否 | 用户时区与时段 | 是 |
| `FEEDBACK_REVOKED` | 取消此前明确反馈 | 原 feedback | 不适用 |

`InterruptionFeedback` 必须保存 `feedbackId`、`briefId`、来源（通知/发现页/L1）、事件、主题作用域、策略版本、发生时间、过期/撤销时间和理由（如有）。不确定主题相似度时只抑制当前 brief，不扩大为长期主题屏蔽。

## 4. 必测反例

1. OEM 压制横幅后，发现页仍有 L1，且没有新增负反馈。
2. 用户选择“稍后”后，未到期不重发；到期且已离开内容上下文时不补发 heads-up。
3. 用户撤销主题屏蔽后，后续符合完整 L1 门的同主题内容可以再次参与策略。
4. 同一 `LearningMoment.interventionKey`、普通 package/scope/interest/graph 修订和重投均不能消耗第二次通知额度；该 key 固定为 `l1:learnerId:momentId:NORMAL`，不得含 scope hash、package revision 或 assessment ID。
5. 媒体 episode 默认只有一个普通 slot。仅当受控策略同时证明“不同重大 learning anchor”与“学生已主动进入或订阅”时，才能原子预留第二个 slot；图谱补全、student patch、权限恢复、OEM 阻断或延后重试都不能获取/退还 slot。
6. `POSTED`、`DEFERRED`、`SUPPRESSED_CONTEXT`、权限/OEM 阻断只是 `NotificationAttempt` 状态，不能删除、撤回或重建 Discover 中的 LearningMoment。实质错误使用独立、限额的 `CORRECTION` key，不与普通 slot 混用。

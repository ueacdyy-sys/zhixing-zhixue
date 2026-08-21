# L3 题目与独立校验契约

## 1. `QUESTION_ITEM.v2` 最小结构

```json
{
  "questionId": "q_...",
  "packageId": "cap_...",
  "packageRevisionId": "caprev_...",
  "prompt": "...",
  "choices": [{"id": "A", "text": "..."}],
  "correctChoiceIds": ["A"],
  "explanation": "...",
  "scoringRule": {"type": "exact-choice", "version": "..."},
  "evidenceIds": ["evidence_..."],
  "generator": {"id": "...", "version": "...", "runId": "..."},
  "validationId": "validation_...",
  "publishState": "DRAFT"
}
```

题干、所有选项、答案、解析、判分规则和证据均不可只引用同一次模型的自然语言输出。任何字段变动必须生成新 `packageRevisionId` 和新 validation，不得静默覆盖学生已见版本。

## 2. `QUESTION_VALIDATION.v2` 最小结构

```json
{
  "validationId": "validation_...",
  "questionId": "q_...",
  "status": "UNVERIFIED",
  "method": "RULE | AUTHORITATIVE_SOURCE | HUMAN_REVIEW",
  "validator": {"id": "...", "version": "...", "runId": "..."},
  "answerEvidence": [{"sourceId": "...", "locator": "...", "excerptHash": "..."}],
  "validatedAt": "...",
  "revokesValidationId": null,
  "reason": null
}
```

- `validator` 不能与生成该题的同一生成 run 相同；若使用模型辅助，验证必须再有确定性规则、权威来源比对或人工复核之一。
- 仅 `VERIFIED_BY_RULE` 或 `VERIFIED_BY_SOURCE` 能把 question 转为 `PUBLISHABLE`。`UNVERIFIED`、`REJECTED`、`REVOKED` 绝不对学生开放。
- 依据、校验器或题目内容被撤销时，写入新的 `REVOKED` validation，题目 `WITHDRAWN`，停止新答题/判分；历史答题保留当时题目、答案、校验版本和显示状态，不能篡改为新结果。
- 离线时允许保存学生输入，但 answer record 只能为 `LOCALLY_RECORDED_PENDING_RECONCILIATION`，必须固定 question/package/validation/curriculum alignment/consent generation。恢复联网后重新核对当前可用性：通过才 `FINALIZED`，撤销、跨 scope、课程不适配或授权 fence 失败即 `REJECTED_REVOKED`；未最终化不得显示最终分数、写长期索引或形成掌握结论。L4 同样只可 `QUEUED`，收到同版本、同 scope 的 delivery receipt 后才 `DELIVERED`。

## 3. 负向验收

1. 出题模型的“自我确认”不构成有效 validation。
2. 正确选项与来源摘录不一致时 `REJECTED`，L3 页面不可进入。
3. 已发布题目撤销后，深链、缓存和离线队列都显示不可继续，而不是继续以旧答案给分。

# 证据卡、正式作答与受控资源契约

## 1. `EVIDENCE_CARD.v2`

```json
{
  "cardId": "ecard_...",
  "learnerId": "learner_...",
  "sessionMode": "DAILY_INTEREST | POST_ASSESSMENT_REVIEW",
  "episodeId": "episode_...",
  "assessmentId": null,
  "facts": [{"factId": "...", "evidenceIds": ["..."], "statement": "可观察事实"}],
  "interpretations": [{"claimId": "...", "statement": "可能解释", "supportIds": ["..."], "counterEvidenceIds": [], "status": "PROPOSED"}],
  "gaps": [{"code": "AUDIO_UNRESOLVED", "detail": "..."}],
  "curriculumRefs": [{"resourceId": "...", "version": "...", "license": "..."}],
  "confidence": {"policyVersion": "...", "value": "policy-owned"},
  "reviewStatus": "PENDING | VERIFIED | NEEDS_REVIEW",
  "suggestedActions": ["OPEN_L1 | SAVE | UNPROMPTED_PRACTICE | HUMAN_REVIEW"]
}
```

事实、解释、反证、缺口和建议是不同字段。模型不得把解释写入事实字段；无支持/有冲突的解释只能 `PROPOSED/NEEDS_REVIEW`。日常兴趣的 card 可承载 L1 的来源说明，但不替代 `CONTENT_ANALYSIS_PACKAGE.v2` 的唯一入站主键约束。

## 2. 正式作答模式

- `ASSESSMENT_SESSION_OPENED.v2` 必填 learner、任务/题目 `CurriculumResource` 版本、授权、时钟域和 `sessionMode=FORMAL_ASSESSMENT`。
- PC/Android/云的 notification outbox、practice outbox、correction outbox 与即时干预服务收到该 mode 时必须拒绝发送；进入 mode 时必须以 `FORMAL_ASSESSMENT_FENCE` 事务取消/抑制该 learner 已 pending、deferred、retry 的触达，取消已 posted 通知并使深链只读拒绝。拒绝本身写审计，不能依赖 UI 隐藏或等下一次轮询。
- `ASSESSMENT_SESSION_CLOSED.v2` 后才可生成 `POST_ASSESSMENT_REVIEW` card。错误题、答对但不稳定、证据冲突三类结论都要有不同 action；不能把状态质量线索单独升级为掌握度或诊断。

## 3. `CurriculumResource`

资源至少包含 subject、grade、resourceId、version、license/source、知识点、题目材料、标准答案或评分点（若适用）。L3、正式复盘和掌握趋势只能引用明确版本的受控资源，且必须有 `CurriculumAlignment` 证明当前 learner 的学段/学科/概念与资源适配；外部网页可作 L2 背景补充，不能悄悄变成标准答案或评分依据。没有适配资源时 L3/课程性复盘保持 unavailable，不用通用模型题替代。

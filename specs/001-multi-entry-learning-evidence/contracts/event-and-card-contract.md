# 事件与证据卡契约

## Event

```json
{"event_id":"evt_*","session_id":"ses_*","task_id":"task_*","source":"pc|phone|glasses|wearable","modality":"behavior|media|vision|biosignal","event_type":"read|seek|edit|pause|revisit|submit|self_report","start_ts":"ISO-8601","end_ts":"ISO-8601","confidence":0.0,"quality_flags":[],"evidence_uri":"local://...","privacy_level":"local_only|masked","review_status":"auto|human_checked|disputed"}
```

## EvidenceCard

```json
{"card_id":"card_*","window_id":"win_*","facts":["evt_*"],"interpretation":"可能解释","counterevidence":[],"uncertainty":[],"confidence":"high|medium|low","action":"可执行动作","review_status":"auto|approved|disputed","downgrade_reason":null}
```

硬规则：`facts` 为空时禁止出现高置信解释；`quality_flags` 含 `signal_quality_low`、`time_uncertain` 或 `evidence_incomplete` 时必须记录降级；状态模态不能单独创建结论卡。

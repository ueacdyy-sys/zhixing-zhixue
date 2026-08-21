# 策略可信、证据完整性与多端生命周期契约

## PolicyBundle

所有策略以签名 `PolicyBundle` 发布。bundle 至少含内容 hash、批准主体、签发/到期时间、撤销代次、允许的客户端/网关 schema、`SemanticQualityPolicy`、安全、通知、课程、保留与删除策略版本。客户端和网关在加载、创建 session、处理消息、投递通知和恢复 outbox 时验证签名、有效期、撤销代次与兼容 profile。

策略验证失败、过期、撤销或不兼容时一律失败关闭：不外发媒体、不产生/投递 L1、不最终化 L3/L4、不继续导出。若新 bundle 改变安全、授权、质量或课程适配结论，尚未呈现的 package 必须重评；已呈现内容保留版本审计，并按既有更正/撤回语义处理。

`PolicyTrustRoot` 是 bundle 验签的唯一根。根记录 key epoch、过渡期、撤销状态和最小软件版本；新根只能由当前有效根或独立紧急撤销根签发。客户端/PC/云拒绝未知根、已撤销根、过期过渡根、epoch 回退和无法验证撤销列表的 bundle。根轮换本身也写入 `EvidenceIntegrityLedger`，不能通过本地配置覆盖静默替换。

## EvidenceIntegrityLedger

每个 ledger entry 包含 `learnerId`、session/episode/scope、父 entry hash、payload hash、PolicyBundle hash、设备/服务 key id、签名、单调序列与可比对时间锚点。媒体 range、L0 facts、assessments、package revisions、student actions、notification attempts、export/deletion receipts 均追加进入链。验证失败、父链缺失或重放产生 `BROKEN/QUARANTINED`，不得用于 L1/L3/L4 正式结论、导出或竞赛“真实闭环”声明。

`LedgerCheckpoint` 定期把 ledger head、单调序列、key epoch、受控存储证明和 `TimeAuthority` 状态写入不可回退安全存储；PC/云可用时追加跨端 receipt。恢复、换机、备份导入和离线重放必须验证 checkpoint 连续性，无法证明即 `UNKNOWN/QUARANTINED`，不能补写或重排序成“已验证”。

`TimeAuthority` 把 PTS/单调时钟与可信墙上时间分离。没有可信墙上时间时，媒体仍可按单调顺序处理，但保留删除、token/lease、quiet-hours 解除、到期和竞赛延迟进入保守状态：抑制通知、不误删、显示待校准原因。不得仅相信用户可调整的设备时间。

## 多设备控制

`CaptureOwnershipLease` 以 `learnerId + sourceKind + physical/source session` 为键，只有当前 epoch owner 可上传或续传该 source；并行手机、眼镜、PC 允许作为不同 source，但不能竞争同一 source。`LearnerDeliveryAuthority` 指定唯一主手机；L1 intervention 的 notification attempt 必须绑定 authority epoch。换机、撤销、恢复或竞争时先撤销旧 lease/authority，再发新 epoch；旧设备请求只可失败关闭。

## 协议和备份删除

`ProtocolCompatibilityProfile` 明确每个 schema/capability 的允许范围和弃用期限。不兼容只能提示升级/不可用，禁止协议降级、字段猜测或使用 `candidate_card.v1` 兜底。

`BackupDeletionManifest` 将删除根展开为主存储、缓存、对象、向量/搜索索引、分析聚合、冷备份/灾备和每 session 加密密钥。备份暂不能物理删除时必须先撤销唯一解密密钥并记录不可读 receipt；任何恢复任务在暴露数据前强制重放最新 tombstone/fence。没有 manifest 终态，不得把删除任务标为完成。

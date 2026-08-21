# CaptureTransport：媒体与时间契约

RTSP 是媒体 data plane，`AnalysisTransport` 是控制、行为、投递与 ACK plane；两者必须由同一个 `captureSessionId` 和 `learnerId` 绑定。RTSP 只是编解码/会话语义名称，不构成允许明文传输的例外。

## 会话握手

`CAPTURE_SESSION_OPENED.v2` 必填：`captureSessionId`、`learnerId`、`consentId`、`consentGeneration`、source、授权快照、PTS epoch、单调时钟锚点、时钟域、策略版本、媒体流 endpoint/lease、最大缓存额度与来源过滤版本。它还必须带 device credential key id、短期 token 的到期时间、`MediaSecuritySession`（加密套件、双向身份、分片 MAC key reference、anti-replay cursor）和持久 `userCaptureEnabled` 快照；旧 capture API 只传 RTSP port/path 的请求不得进入 v2 分析链。

`capturePolicy` 最小字段为 `captureScope`（仅 `SYSTEM_SINGLE_APP` 或 `WHOLE_SCREEN`）、用户确认的目的地（PC local / future cloud）、未知/敏感画面决策、过滤器版本和 consent 引用。系统不得从像素流假称已识别第三方应用或视频 ID；视觉/文本过滤无法可靠判定时必须产生 `PAUSE_PENDING_USER` 或 `BLOCK_TRANSPORT`，而非继续向 PC/云发送。

## 媒体分片

每个分片必填：序列号、PTS 范围、epoch、媒体哈希、音轨状态、`AudioCapabilitySnapshot` 引用、session/source/learner/consent generation、开始/封存/到达时间、clock mapping、range hash、认证标签。PC 在解密、身份、scope、consent fence、序列和 MAC 全部通过后才以序列号和哈希 ACK/NACK；Android 仅删除已 ACK 且未被撤回约束的缓存。过期、重放、scope 不匹配、撤回 generation 或认证失败的分片必须拒绝并审计，绝不尝试明文重传。

`AudioCapabilitySnapshot` 必须声明 `capturePath=PLAYBACK | MICROPHONE | MIXED | NONE`、系统/应用允许状态、用户是否显式同意麦克风、音画同步估计与关键语义覆盖。对手机屏幕视频，只有 `PLAYBACK` 且同步通过可作为“同源播放音频”满足关键语音门；`MICROPHONE` 或 `MIXED` 默认不能把环境声、他人声音或扬声器回录当作已验证播放音频，也不能在播放捕获失败时自动启用。眼镜第一视角的环境音适用其独立 source/consent，但同样必须明确来源与缺口。

## 断连、续传与流控

- 续传以 `resumeCursor = epoch + sequence + rangeHash` 确认，重发必须幂等。
- PC 不可用时 Android 进入缓存状态；不得切云。若用户已停止、解绑、撤回或 device credential 被撤销，缓存/续传也必须停止并进入对应删除或显式保留状态，不能在服务重启后继续发送。
- 缓存水位达到 soft limit 时降低非关键处理并提示；达到 hard limit 时受控暂停采集/等待用户，不得删除已封存分片。
- 媒体、行为、L0 facts 都记录原始时间与时钟映射；融合前检查不确定度阈值。
- 媒体 endpoint 只能由已认证会话派生；禁止可猜测公网/局域网 path、未绑定 listener、通配符 receiver 或将真实流暴露给未配对设备。密钥/认证材料不得写日志、通知、URL query 或持久化到公共目录。

## 结束与撤回

`CAPTURE_SESSION_CLOSED.v2` 只结束采集；`CONSENT_REVOKED.v2` 与 `DELETE_REQUESTED.v2` 触发删除协议。撤回后所有未 ACK/未完成的上传、worker 和 enrichment job 必须取消。

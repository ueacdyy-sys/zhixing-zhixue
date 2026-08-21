# 同意、证据与删除契约

## CloudDataPolicy

在 policy 未冻结时 `CloudAnalysisTransport` 必须为 disabled，不能发送任何媒体、转写、行为、图谱或画像。正式开启必须定义：数据类别 allowlist、显式 `ConsentReceipt`、设备/服务身份认证、传输/静态加密、区域、保留期、额度、撤回级联与 `DeletionReceipt`。

## 本地保护、保留与设备撤销

- 原始媒体、音频、转写、evidence locator 的可展示派生物和 outbox 只能放在应用/PC 服务私有存储；不得写入公共相册、下载目录、明文临时目录或通知正文。密钥由 Android Keystore/PC 受控密钥存储管理，日志只写哈希和脱敏诊断。
- 每个 capture session 创建不可变 `RetentionPolicySnapshot`，明确对象类别、到期时间、自动清理任务和法定/用户明确保留理由。正常 `CaptureSessionClosed` 只按该快照结算，不等于永久保存；到期清理也必须写 receipt。
- 配对设备、证书 pin、会话 token 和本地密钥均要有设备身份、版本、轮换、失效和丢失设备撤销语义。首次配对只建立 Keystore 中不可导出的设备凭据；PC 以该凭据证明签发短期访问 token，token 到期必须刷新或显式重新配对，禁止仅凭旧 bearer 无感延长有效期。撤销配对立即停止该设备的媒体/控制访问，废弃未完成 lease、取消 capture worker/outbox/enrichment，并按 consent 触发删除；不能仅隐藏 UI、让后续请求 401 或等待 token 自然过期。
- “停止同步/采集”是独立的持久用户意图，不等于网络临时失败或 Android 服务被系统回收。前台服务重启、进程恢复和自动 DHCP 重连均必须先检查该意图；停止后不得恢复轮询、capture session、通知 outbox 消费或自动重连，只有用户显式重新开始才可恢复。
- `LearnerScope` 与 device pairing 分离：本地模式以受控的本地 learner id 隔离资料，换设备/迁移不可自动并入；云模式只有在用户完成认证、明确绑定 scope 并授予云 consent 后才可创建。PC 多设备、共享电脑和恢复备份时都必须校验 scope，禁止把 device id、token 或文件路径当作学生身份。
- scope 隔离是强制的存储和授权边界：每张业务表的主键/唯一键、outbox lease、evidence resolver、图谱 revision/patch、通知和删除 target 都必须包含 `learnerId` 或受其复合 FK 约束；跨 scope message、ACK、深链、缓存命中、导出和删除一律失败关闭。换机只能走显式、可审计的 scope transfer，不能由同一 PC、IP、token 或备份文件自动合并。

## 移动端采集 allowlist 与受控导出

- 手机采集模式必须区分“学生主动开启的主流流媒体会话”和默认关闭的行为事件能力。聊天、支付、相册、浏览器私密内容、输入态、密码、URL、剪贴板、锁屏和未知来源一律在编码、缓存与外发前阻断；误入缓存的无关内容立即删除并留下不含内容的审计事件。
- `ControlledEvidenceExport` 只能导出与一个 learner scope、会话和明确目的绑定的脱敏证据卡/复盘摘要。请求必须包含发起者、接收方、目的、字段 allowlist、到期与撤回；原始媒体、原始 EEG/手表流、完整画像、聊天和浏览史默认禁止。导出接收方不获得 live 数据访问权，撤回后下载/解析链接失效并写 receipt。

## EvidenceLocator

`local://` 仅为 owner 本地实现细节，不能直接由 Android 渲染。跨端引用必须提供：`contentHash`、owner、resolver、授权范围、短期 token/expiry、可展示的脱敏派生物、availability 与删除状态。撤回后 resolver 返回 `REVOKED`，不泄露路径或残留内容。

## 删除级联

删除 root 为 `consentId` 或 `captureSessionId`。目标集合固定包含：原始媒体、Android/PC 缓存、上传 outbox、worker 任务、L0 facts、brief/package、graph revision、source excerpt、notification outbox、personal index 与云端对象（若已启用）。每端写 `DeletionReceipt`；未确认目标保持 `DELETE_PENDING` 并按 policy 重试，超过 deadline 或遇不可重试错误转 `DELETE_ESCALATED`，不能无限静默等待。内容 tombstone 不可再被 UI、检索或分析读取。

撤回首先原子写入单调 `ConsentFence`，再启动异步删除：所有 ingress、worker、outbox、ACK、缓存恢复、图谱 patch、通知执行与 evidence resolver 在入口和提交前比较 generation。旧 generation 的在途/重放消息只能写入不含内容的拒绝审计，不能因删除尚未完成而重新落库、投递或延长 lease。

Android 删除执行器还必须取消每个已 `POSTED` 的 L1 `NotificationManager` 记录，持久化 `CANCELLED_REVOKED` 与 notification key；取消失败同样属于删除 target。取消后 deeplink、PendingIntent receiver、离线 package cache 和发现页查询都必须拒绝读取已撤回 brief。

## WebEnrichmentConsent

联网补全需单独可见开关与 `ConsentReceipt`。每次查询记录最小锚点、查询清单、来源策略/allowlist、预算、取消和关联删除任务。断网、未同意或预算耗尽时只保留本地内容图谱。

## 学生安全与授权主体

`ContentSafetyAssessment` 是 L1 的独立前置门，不是用户画像或诊断。它只能给出 `LEARNING_SAFE`、`RECORD_ONLY`、`REQUIRE_HUMAN_REVIEW` 或 `BLOCK_INTERVENTION`；对疑似成人、暴力、自伤、违法危险、私密或无法安全解释的内容默认不做高优先级学习介入。策略必须有版本、最小理由码、复核/纠错入口和误判回归集，不得保存不必要的敏感内容类别标签。

普通 capture consent 不能代替处理敏感个人信息、未成年人信息或云端分析所需的适用授权。启用这些路径前必须由产品合规流程确定授权主体、监护授权（如适用）、最小必要范围、保留期、撤回方式与区域；结果持久化为 scope-bound `ProcessingEligibilityGrant`，状态只能为 `ELIGIBLE/UNAVAILABLE/REVOKED/EXPIRED`。所有 ingress、任务恢复、通知、云端和导出使用同一 grant resolver；缺少有效结果时 capability 保持 disabled，不传输也不做介入，不得从设备、年级或历史资料推断资格。

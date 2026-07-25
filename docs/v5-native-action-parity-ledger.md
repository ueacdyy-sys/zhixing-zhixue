# V5 网页到原生交互对照账本

基准：`design/mobile-ui-prototype-v5/index.html` 最终覆盖层（不是旧函数残留）与 `review-gallery.html` 48 个状态。  
判定：**已核验**=真机已完成点击前/后/系统 Back；**已实现待真机**=原生有状态变化和目标页但尚未截图；**差异**=规则不同；**未实现**=无可见入口或无状态变化。

## 本轮实测证据（2026-07-24）

- 真机：`ANG-AN00`，无线 ADB `172.27.13.55:5555`；当前已取得 54 个 QA 状态截图，目录为 `mobile-edge/artifacts/v5-native-ui-audit/2026-07-24/round4/all-pages/`。
- 网页基准：`design/mobile-ui-prototype-v5/index.html` 最终覆盖层。静态动作名共 72 个，其中 14 个属于被后续连续对话工作台覆盖、当前不可达的旧智能体模板，不能当作待迁移需求。
- 已执行真机返回测试：启动 `setting:显示`，执行 Android 系统 Back；结果为设置抽屉重新打开，抽屉外仍可点击关闭。截图：`mobile-edge/artifacts/v5-native-ui-audit/2026-07-24/interaction-recheck/settings-display-after-system-back.png`。
- 已修复但尚待新版安装复验：不完整证据（含当前眼镜封存记录）点击后只显示“仅保留记录”的明确反馈；不得建立 L0–L4 路径。公开媒体会话、视频、音频、网络从抽屉直接进入真实 RTSP/DataStore 控件页，页面返回和系统 Back 都回到同一抽屉。

## 尚存的规则差异（不能按“已对齐”验收）

1. **统计筛选没有驱动图表数据**：原生筛选页只更新已选范围文案；网页规则要求应用筛选后统计范围和图表数据同步变化。
2. **图谱管理只有入口，没有完整管理动作**：检索可执行，但“未链接提及、待审核建议、版本历史、回收站”仍未分别成为可操作的管理视图。
3. **设备详情职责过度合并**：PC、眼镜/EEG、手表当前仍共享概述页；网页要求按设备类型分别表达控制链、数据链、离线回退、时间同步和质量边界。
4. **智能体资料库层级尚未逐动作复验**：需要在真机验证“文件与资料 / 发现会话 / 知识库”三个 tab 的不同主体、回发现多选的往返状态、引用 chip 移除以及新对话清空引用。
5. **全屏画布和节点编辑需基于新版真机复验**：虽然原生已将内容关系图、长期知识图和统计图拆为不同画布，但仍要验证拖拽后重进、边缘锚点和右缘加号位置全部使用同一布局状态。

| 网页动作 | 网页规则 | 原生当前规则 | 当前判定 / 修复动作 |
|---|---|---|---|
| nav | 一级导航不进入详情栈 | 一级状态切换 | 已实现待真机 |
| drawer-open / drawer-close | 抽屉、点遮罩关闭 | 236dp 抽屉、遮罩关闭 | 已实现待真机 |
| back | 回到真实父页 | BackHandler + 三元历史栈 | 已实现待真机，须逐路径截图 |
| set-stream | 发现页内切手机/眼镜流 | 同页切 `PHONE_SCREEN/GLASSES_FIRST_PERSON` | 已实现待真机 |
| open-message | 完整证据进学习，非完整仅记录 | 非完整原型仍可进 L0 | 差异：需改为明确仅记录反馈 |
| open-glass-message | 第一视角内容路径 | 第一视角候选内容页 | 已实现待真机 |
| glasses-session-detail | 进第一视角封存/同步详情 | 已改进状态流与同步详情 | 已实现待真机 |
| show-banner / banner-dismiss / banner-open | L1 横幅显示、关闭、打开 | 同页横幅状态 | 已实现待真机 |
| selection-toggle / select-session / selection-cancel | 发现多选会话 | 同页多选集合 | 已实现待真机 |
| selection-delete | 移入回收 | 本机回收集合 | 已实现待真机 |
| agent-from-sessions | 将选中快照带给智能体 | 写入只读引用 | 已实现待真机 |
| set-level / advance | 学生自愿 L0-L4 | 真实包门控；QA 仅渲染不写库 | 已实现待真机 |
| evidence-detail / sources / source-open | 各自有详情并准确返回 | 独立二级路由 | 已实现待真机 |
| set-map | L2 思维导图/知识图谱切换 | 两套内容关系布局 | 已实现待真机 |
| node-detail | 内容节点进概念说明 | 已改为 `CONCEPT_DETAIL`，不误写长期知识库 | 已实现待真机 |
| canvas-fullscreen | 当前画布全屏且保留模式 | 内容/知识/统计分支全屏 | 已实现待真机 |
| answer-choice / submit-answer | L3 选择反馈、L4 非空回执 | 真实内容包+回执仓储 | 已实现待真机 |
| set-profile-mode | 知识全览/学习分析统计切换 | 同级模式 | 已实现待真机 |
| set-chart | 六张不同图 | 六个独立 Canvas 分支 | 已实现待真机 |
| profile-filter / filter-set | 筛选改变统计范围 | 当前只保存选择文案 | 差异：筛选未接入统计数据 |
| profile-evidence / evidence-row | 证据索引和明细 | 独立路由 | 已实现待真机 |
| knowledge-open | 节点进编辑 | 节点详情页 | 已实现待真机 |
| knowledge-child / knowledge-create-save | 节点右缘加号、创建子节点并显示边 | 写知识库、建 PART_OF 边 | 已实现待真机 |
| knowledge-save / knowledge-ai-accept | 保存笔记、确认建议 | 仓储写入/确认 | 已实现待真机 |
| knowledge-link | 写双向关系 | 生成双向 RELATED_TO 边 | 已实现待真机 |
| knowledge-rename / knowledge-delete-confirm | 改名/回收 | 仓储改名/移入回收 | 已实现待真机 |
| knowledge-source-open | 来源证据页 | 独立二级页 | 已实现待真机 |
| knowledge-tab | 笔记/双向链接/来源证据 | 已补三 tab | 已实现待真机 |
| knowledge-search / knowledge-search-run | 入口、查询结果 | 已补入口和本机查询 | 已实现待真机 |
| knowledge-tools / knowledge-tool-action | 管理入口及真实管理视图 | 仅“已定位”文字 | 未实现：必须补真实管理列表 |
| route-setting / setting-select / toggle-setting | 七类设置和控件 | 显示/媒体实际绑定，通知/隐私部分欠缺 | 部分：按设置页逐项核验 |
| setting-route / delete-audit | 进入通知历史、导出、审计 | 独立页 | 已实现待真机 |
| export-confirm | 确认导出 | 无真实导出适配器 | 未实现：保持不伪造成功 |
| session-detail / toggle-session | 会话详情、开始/停止采集 | MediaProjection/RTSP 真实状态 | 已实现待真机 |
| pc-detail / device-detail / sensor-status | PC、眼镜/EEG、手表分别说明链路 | 当前设备页仍合并为概述 | 差异：需按设备类型拆卡 |
| agent-new-chat | 清空当前会话引用 | Workspace 清空 | 已实现待真机 |
| agent-library / agent-view-chat | 独立资料库/返回对话 | 已有切换，层级仍需视觉比对 | 部分 |
| agent-library-tab | 文件/发现会话/知识库三种主体 | 当前待逐 tab 真机核验 | 已实现待真机 |
| agent-open-file-picker / agent-file-remove | 本地队列的添加/移除 | SAF 多选、队列移除 | 已实现待真机 |
| agent-add-knowledge / agent-remove-reference | 引用、移除引用 | Workspace 状态变更 | 已实现待真机 |
| agent-open-discover-selection | 回发现多选 | 切发现并打开多选 | 已实现待真机 |
| agent-toggle-network / agent-send | 联网状态、发送真实请求 | 真实 PC 网关失败语义 | 已实现待真机 |

## 禁止混淆

- 网页中被最终 `agent=function(){...}` 覆盖的旧 `agent-mode`、`agent-run-search`、`agent-run-answer`、`agent-file-type`、`agent-generate-file`、`agent-download-file` 不是当前可见动作，不能误算为原生遗漏。
- QA Activity 只为可重复截图渲染预览层级；它不代表生产环境的 L1-L4 已被解锁，也不得写入正式学习、知识或智能体记录。

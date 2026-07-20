# 实施计划

1. 在框架无关的运行时领域层增加 `VisitSemanticState` 与 `VisitSemanticProjector`，输入只接受现有 `FusedCandidate`。
2. 为投影器编写先失败的单元测试，覆盖追加性、PTS 排序、visit 隔离、关闭后的呈现资格和三模态门控。
3. 在三 lane worker 完成融合处发布持久化的 `FusedCandidate` 事件；投影器消费事件并写入可重放状态日志。
4. 定义 PC→手机的版本化候选卡契约；当前诊断广播只用于验收，不作为正式链路。
5. Android 实现候选列表、L1 概念浅讲、L2 延伸资料、L3 讲解练习、L4 无答案自主练习，以及本地回执。
6. 以连续真机流验证：播放期间产出候选状态、滑动/回看边界正确、旧 visit 不误触发当前提醒。

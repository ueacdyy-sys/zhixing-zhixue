# 实时理解前置实验：PC侧解码与关键帧抽样 - 2026-07-08

## 本轮真实目标

在不重新进入短视频或私人页面的前提下，基于已保存的 ScreenStream RTSP 录制文件，验证 PC 侧是否能够稳定完成：

```text
RTSP/H.264录制文件 -> PyAV解码 -> 关键帧抽样 -> 感知哈希去重 -> 输出关键帧与JSON报告
```

本轮仍不做语义理解、不生成微任务，只验证实时理解链路的前置数据消费能力。

## 输入样本

- 样本文件：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\rtsp_record_20260708_150115\rtsp_8s_copy.mkv`
- 来源：华为 JNY-AL10 上 ScreenStream RTSP 模式
- 样本内容：ScreenStream 自身设置页，不包含短视频、聊天、支付、相册等私人内容
- 既有采集参数：H.264，约 508x1088，约 30 FPS

## 新增脚本

- 脚本：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\scripts\rtsp_frame_sampler.py`
- 实时等待脚本：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\scripts\live_rtsp_sampler_probe.py`
- 运行环境：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\env\py311`
- 依赖确认：
  - PyAV `16.1.0`
  - OpenCV `5.0.0`
  - Pillow 可用
  - ImageHash `4.3.2`
  - NumPy `2.4.6`

脚本能力：

1. 支持本地视频文件或 RTSP URL 作为输入。
2. 使用 PyAV 解码视频流。
3. 按目标间隔抽取关键帧，当前测试间隔为 `0.75s`。
4. 使用 perceptual hash 判断相邻关键帧是否重复。
5. 输出 JPEG 关键帧和 `sampler_report.json`。

## 测试一：启用去重

命令核心参数：

```text
--target-interval-s 0.75
--dedup-hamming-threshold 4
```

输出目录：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\frame_sampler_probe_20260708_1600
```

结果：

- 解码帧数：`217`
- 输出关键帧：`1`
- PTS估计视频时长：`7.202s`
- 原始流估计帧率：`30.13 FPS`
- 离线解码吞吐：`97.40 FPS`

解释：

该样本画面基本静止，感知哈希认为连续抽样帧高度相似，因此只保留第一张关键帧。这个结果说明去重逻辑能减少静态画面重复进入后续模型。

## 测试二：关闭去重验证抽样节奏

命令核心参数：

```text
--target-interval-s 0.75
--dedup-hamming-threshold 0
```

输出目录：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\frame_sampler_probe_no_dedup_20260708_1600
```

结果：

- 解码帧数：`217`
- 输出关键帧：`10`
- PTS估计视频时长：`7.202s`
- 原始流估计帧率：`30.13 FPS`
- 离线解码吞吐：`209.54 FPS`
- 原始帧间隔中位数：`0.033s`
- 关键帧间隔中位数：`0.767s`

关键帧目录：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\frame_sampler_probe_no_dedup_20260708_1600\keyframes
```

可视检查：

- 首张关键帧可打开。
- 画面为 ScreenStream 设置页。
- 未见黑屏、损坏或乱码。

## 本轮证明

1. PC侧可以对已保存的 RTSP/H.264 手机画面流进行稳定解码。
2. 离线解码吞吐明显高于原始流帧率，说明在当前样本上，解码不是第一瓶颈。
3. 按 `0.75s` 抽样可以形成约 `0.767s` 中位间隔的关键帧序列。
4. 感知哈希去重能识别静态画面，避免重复帧进入后续OCR或视觉模型。
5. 本轮输出的 JSON 报告和关键帧目录可以作为后续 OCR/字幕/画面理解模块的输入。

## 本轮没有证明

1. 没有证明实时 RTSP 流接入的端到端延迟，因为本轮使用的是保存文件。
2. 没有证明真实短视频内容理解能力。
3. 没有证明音频、字幕、画面三路融合。
4. 没有证明微任务生成质量。
5. 没有证明手机端反馈闭环。
6. 没有证明用户刷视频时系统不会造成卡顿。

## 下一步推进

已经尝试重新开启 ScreenStream RTSP。第一次尝试时，手机弹出系统录屏授权窗口，但用户当时不在现场；为避免越过敏感授权边界，未通过 ADB 代点“允许”，并已取消授权、停止 ScreenStream。

第二次尝试在用户返回后进行，用户完成授权，实时 RTSP 测试通过。

## 测试三：实时 RTSP 输入，启用去重

命令入口：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\scripts\live_rtsp_sampler_probe.py
```

实时输入：

```text
rtsp://10.26.122.39:8554/screen
```

输出目录：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\live_rtsp_sampler_probe_20260708_164441
```

结果：

- 采样时长目标：`10s`
- 解码帧数：`302`
- 输出关键帧：`1`
- PTS估计时长：`10.0036s`
- 原始流估计帧率：`30.19 FPS`
- 实时解码吞吐：`33.11 FPS`

解释：

实时输入下，PC侧能跟上约30 FPS的RTSP/H.264流。由于画面仍是ScreenStream设置页，感知哈希去重后只保留1张关键帧，符合静态页面预期。

## 测试四：实时 RTSP 输入，关闭去重验证抽样节奏

输出目录：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\live_rtsp_sampler_probe_no_dedup_20260708_1645
```

结果：

- 解码帧数：`302`
- 输出关键帧：`15`
- PTS估计时长：`10.0002s`
- 原始流估计帧率：`30.20 FPS`
- 实时解码吞吐：`33.05 FPS`
- 原始帧间隔中位数：`0.0335s`
- 关键帧间隔中位数：`0.7670s`
- 首张关键帧可视检查正常，画面为ScreenStream设置页。

## 实时测试收尾

- 已执行 `am force-stop info.dvkr.screenstream.dev`。
- 后续检查未发现 Windows 侧 `8080/8554` 监听。
- Wi-Fi ADB 仍保留为 `10.26.122.39:5555 device`。

## 当前实时链路结论

1. 在用户手动授权录屏后，ScreenStream RTSP实时流可以被PC侧直接消费。
2. 当前PC侧PyAV解码能跟上约30 FPS输入，10秒实时采样未掉到实时以下。
3. `0.75s`关键帧抽样在实时流上可用，关键帧间隔中位数约`0.767s`。
4. 感知哈希去重能把静态画面压缩为单帧，后续可减少OCR/视觉模型调用。
5. 这一步已经从“录制文件可处理”推进到“实时RTSP流可处理”。

## 测试五：关键帧OCR探针

新增脚本：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\scripts\keyframe_ocr_probe.py
```

OCR依赖：

```text
rapidocr-onnxruntime
```

输入目录：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\live_rtsp_sampler_probe_no_dedup_20260708_1645\keyframes
```

全屏OCR结果：

- 输出目录：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\ocr_probe_full_live_20260708_1655`
- 处理帧数：`5`
- 引擎初始化：约`0.76s`
- 单帧耗时中位数：约`1.30s`
- 单帧耗时范围：约`1.13s`到`7.31s`
- 可识别内容包括：`选择串流模式`、`RTSP模式`、`RTSP服务器地址`、`rtsp://10.26.122.39:8554/screen`、`停止流媒体`等。

底部区域OCR结果：

- 输出目录：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\ocr_probe_bottom_live_20260708_1655`
- 处理帧数：`5`
- 引擎初始化：约`0.74s`
- 单帧耗时中位数：约`0.81s`
- 单帧耗时范围：约`0.78s`到`3.78s`
- 可识别内容包括：`服务器设置`、`视频设置`、`音频设`、`停止流媒体`、`串流`、`设置`、`关于`、`退出`等。

OCR阶段判断：

1. 本机CPU OCR可用，能识别手机画面中的中文和URL。
2. 全屏OCR热启动后约1秒级，但仍不适合对每个`0.75s`关键帧无条件执行。
3. 区域裁剪可以降低耗时，但收益取决于目标文本所在区域。
4. 下一步应把OCR放在“感知哈希变化明显、场景疑似视频页、频率受控”的后级，而不是逐帧全量跑。
5. 对真实短视频，OCR应优先关注标题区、字幕区、搜索/评论入口和明显文本区域；画面主体理解要交给轻量视觉分类或视觉语言模型候选阶段。

仍需注意：

1. 该测试仍在ScreenStream设置页完成，不代表真实短视频页面已经理解。
2. 还没有测试滑动、回看、暂停、进入评论区或切换消息页时的变化检测。
3. OCR已经完成技术探针，但还没有在真实短视频页面上验证标题、字幕和评论区文本识别。
4. 还没有测手机端反馈回路和微任务生成延迟。

下一步应在授权边界内继续测试动态场景，而不是重复证明静态页面可采集。直接使用 `rtsp://10.26.122.39:8554/screen` 作为输入，测试：

1. 打开 RTSP 流耗时。
2. 端到端取帧延迟。
3. 连续取帧稳定性。
4. 滑动或页面变化时，感知哈希是否能及时识别画面变化。
5. 评论区、消息页、设置页、桌面等非视频场景是否会被误判。
6. 抽样频率、去重阈值和 CPU占用之间的关系。
7. OCR/字幕区域识别和轻量视觉分类是否能在 1 秒级内给出候选语义。

可直接执行：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\env\py311\Scripts\python.exe C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\scripts\live_rtsp_sampler_probe.py
```

脚本会启动 ScreenStream、等待手机端手动点击“允许”、确认 RTSP 服务可用，然后执行实时关键帧抽样。

如果实时流测试通过，再接入 OCR/字幕区域识别和轻量视觉分类；不要直接进入大模型微任务生成。

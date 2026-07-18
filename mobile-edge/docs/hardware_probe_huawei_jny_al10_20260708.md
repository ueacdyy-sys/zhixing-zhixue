# Huawei JNY-AL10 Hardware Probe - 2026-07-08

## 本轮真实目标

验证华为手机在授权后，能否支撑“手机前台画面实时采集 -> PC 侧接收/分析 -> 后续反馈”的基础链路，并识别华为/Windows/工具链阻塞点。

本轮只在授权设备和 ScreenStream 自身界面上测试，不进入短视频、聊天、支付、相册等私人内容页面。

## 设备与连接事实

- 手机序列号：`MYQUT20213006206`
- 厂商/型号：`HUAWEI JNY-AL10`
- Android：`10`
- SDK：`29`
- EMUI：`EmotionUI_13.0.0`
- 分辨率/密度：`1080x2310`, `480 dpi`
- Wi-Fi IP：`10.26.122.39/24`
- 电量：30% 起测，后续 31%
- USB ADB：初始需要手动点 RSA 授权；授权后可用
- Wi-Fi ADB：`adb tcpip 5555` 后，`10.26.122.39:5555` 最终变为 `device`
- 当前注意点：切到 ADB TCP/IP 后，USB 设备项显示为 `unauthorized`，Wi-Fi ADB 项可用

## ADB 结论

### USB ADB

结论：可用，但需要给用户足够时间点手机弹窗。

证据：

- 初始状态：`MYQUT20213006206 unauthorized`
- 用户点授权后：`MYQUT20213006206 device`
- 设备属性读取成功：`JNY-AL10`, Android `10`

过程问题：

- 第一次等待窗口太短，导致过早判断 unauthorized。后续所有手机授权弹窗必须留明确等待时间。

### Wi-Fi ADB

结论：可用，适合后续“无数据线控制”实验的基础通道。

证据：

```text
10.26.122.39:5555 device product:JNY-AL10 model:JNY_AL10 device:HWJNY
```

只读检查成功：

```text
adb -s 10.26.122.39:5555 shell getprop ro.product.model -> JNY-AL10
adb -s 10.26.122.39:5555 shell getprop ro.build.version.release -> 10
```

注意：

- `:::5555 LISTEN` 已开启，实验结束或换网络时应主动关闭或切回 USB，避免长期暴露调试端口。

## scrcpy 4.0 测试

结论：不适合作为当前主实验通道。它能初始化视频纹理，但 Windows 端在退出/录制阶段崩溃。

已确认能力：

- 能列出手机编码器：
  - H.264：`OMX.hisi.video.encoder.avc` 硬编、`c2.android.avc.encoder` 软编
  - H.265：`OMX.hisi.video.encoder.hevc` 硬编、`c2.android.hevc.encoder` 软编
- 有窗口模式能初始化：
  - `Renderer: direct3d11` / `opengl` / `software`
  - `Texture: 508x1088`

阻塞证据：

- 多种组合均以 `-1073741819` 退出
- MP4 录制文件为 48 bytes，MKV 为 0 bytes
- `ffprobe` 无法解析这些录制文件

已排除的部分变量：

- 不是单一渲染器问题：`direct3d11`、`opengl`、`software` 都同样崩溃
- 不是单一编码器问题：华为硬编 H.264、软编 H.264、H.265 组合均未解决录制崩溃
- 不是纯手机无法编码：ScreenStream RTSP 后续能稳定输出 H.264

下一步：

- 下载旧版 scrcpy 做版本回归，确认是否为 scrcpy 4.0 + Windows/SDL3 兼容问题。
- 但它不是当前最优推进路线，优先级低于 ScreenStream RTSP / 自研 MediaProjection。

## 系统 screenrecord 测试

结论：该华为机型不能依赖系统 `screenrecord`。

证据：

```text
/system/bin/sh: screenrecord: inaccessible or not found
```

同时：

```text
dumpsys media.codec -> Can't find service: media.codec
```

意义：

- 不能把 Android 原生 `screenrecord` 当作保底方案。
- 必须走 MediaProjection、RTSP/WebRTC 或自研 App 内采集链路。

## ScreenStream MJPEG 测试

结论：链路可用，但性能不适合作为最终实时短视频理解主通道。

安装：

```text
ScreenStream-4.4.1-FDroid-debug-built.apk
Performing Streamed Install
Success
```

包名和入口：

```text
package: info.dvkr.screenstream.dev
activity: info.dvkr.screenstream.SingleActivity
```

MJPEG 服务：

```text
http://10.26.122.39:8080/
WebSocket 返回 streamAddress: stream.mjpeg
```

PC 访问注意：

- 本机有 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`
- 必须用 `curl --noproxy '*'`，否则私网地址会被代理接走，返回 Cloudflare 400

静态采样结果：

- 采样时长：5.423 秒
- 找到帧：23
- 解码帧：23
- 分辨率：`540x1155`
- 约：`4.24 FPS`
- 首帧：`C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\screenstream_mjpeg_probe_20260708_144043\first_frame.jpg`

动态滚动采样结果：

- 采样时长：8.004 秒
- 解码帧：37
- 分辨率：`540x1155`
- 约：`4.62 FPS`
- 帧间隔中位数：`139.3 ms`

源码解释：

- 默认 `RESIZE_FACTOR=50`
- 默认 `JPEG_QUALITY=80`
- 默认 `MAX_FPS=30`
- MJPEG 路线每帧走 `ImageReader -> Bitmap copy/transform -> JPEG compress -> multipart MJPEG`

判断：

- MJPEG 可用于低频页面状态证明、截图式 OCR、调试预览。
- 不适合作为刷短视频实时理解主通道。

## ScreenStream RTSP 测试

结论：当前最有推进价值。RTSP 路线可稳定输出 H.264 约 30 FPS，适合进入后续实时理解实验。

RTSP 地址：

```text
rtsp://10.26.122.39:8554/screen
```

端口状态：

```text
tcp6 ::ffff:10.26.122.39:8554 LISTEN
```

ffprobe 结果：

```text
codec_name=h264
width=508
height=1088
r_frame_rate=30/1
```

8 秒录制结果：

```text
file: C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\rtsp_record_20260708_150115\rtsp_8s_copy.mkv
duration: 8.000000
size: 307606 bytes
frames in ffmpeg log: 217
avg_frame_rate: 30000/1001
```

5 秒解码结果：

```text
frame=127
time=00:00:05.00
speed=1.15x
```

首帧：

```text
C:\Users\Administrator\Desktop\HuaweiCup_PhoneCaptureLab\captures\rtsp_record_20260708_150115\first_frame.jpg
```

判断：

- RTSP/H.264 是当前手机端实时画面流的主实验路线。
- 它符合后续“PC 端作为分析服务器，手机端只做采集/反馈”的方向。
- 后续应围绕 RTSP/WebRTC/自研 MediaProjection 编码链路做性能目标，而不是围绕 MJPEG。

## 当前阻塞与风险

1. scrcpy 4.0 Windows 端崩溃
   - 影响：不能把 scrcpy 录制当主证据链。
   - 处理：降级旧版对照，但不阻塞 RTSP 主线。

2. MJPEG 帧率低
   - 影响：不满足短视频实时理解。
   - 处理：仅保留为调试/低频截图路线。

3. RTSP 尚未测端到端理解延迟
   - 已测的是采集/传输/解码可行性和帧率。
   - 下一步要测“手机画面事件发生 -> PC 收到帧 -> 模型产生候选微任务”的端到端延迟。

4. 音频尚未验证
   - RTSP 目前只确认视频。
   - 短视频理解需要音频/字幕/画面三路融合，下一步需验证系统音频或替代音频路线。

5. 私密/非视频场景防呆未测
   - 还没测前台 App 分类、消息页/桌面/设置页过滤。
   - 后续必须做“只处理授权实验场景，不处理聊天/支付/相册”等防呆规则。

## 下一步推进建议

### P0：采集主链路实验

以 ScreenStream RTSP 作为临时采集源，先搭 PC 侧实时消费管线：

```text
RTSP(H.264, 30fps) -> ffmpeg/PyAV 解码 -> 帧采样/去重 -> OCR/ASR/视觉理解 -> 微任务候选生成
```

最低性能目标：

- PC 侧取帧稳定：目标 15-30 FPS 输入可用
- 语义理解采样：目标每 0.5-1.0 秒抽关键帧，不逐帧上大模型
- 用户停留判断：目标 1-2 秒内识别“当前视频值得跟进”
- 微任务候选：目标 3-5 秒内给出轻量兴趣探索提示

### P1：自研手机 App 方向

ScreenStream 只能证明路线，不应直接等同最终产品。

后续自研 App 应复用思路：

- MediaProjection 获取屏幕
- MediaCodec 硬编码 H.264/H.265
- WebRTC 或 RTSP/自定义低延迟传输
- 前台状态识别与隐私过滤
- 与眼镜第一视角流做时间戳对齐

### P2：眼镜第一视角协同

当前手机 RTSP 只证明“手机载体视频流”。眼镜流还要验证：

- 第一视角摄像头能否同步采集手机屏幕外部过程
- 能否识别“眼睛是否在看手机/手机是否放一边/是否中断”
- 与手机流按时间戳对齐，形成兴趣触发、过程状态、是否半途而废的闭环证据

## 本轮结论

可以推进实验，但推进路线应调整为：

```text
不用 scrcpy/MJPEG 当主路线；
用 RTSP/H.264 作为临时主采集路线；
下一步攻克实时理解与端到端延迟，而不是继续停留在能否抓到画面。
```

## 收尾状态

- 已执行 `am force-stop info.dvkr.screenstream.dev` 停止 ScreenStream。
- 复查后 `8554/8080` 不再监听，避免测试结束后继续推送手机屏幕。
- Wi-Fi ADB `10.26.122.39:5555` 保留为可用控制通道；若不继续实验，应切回 USB 或关闭 TCP/IP 调试。

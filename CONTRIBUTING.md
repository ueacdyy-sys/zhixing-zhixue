# 贡献约束

提交前必须通过：

```powershell
python tools/verify_repository_hygiene.py
python tools/verify_text_encoding.py
```

移动端 Windows 构建从 `C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source` 启动；不得在源码中加入广告、云分析、上游信令、平台私有接口或自动化控制第三方 App 的逻辑。

手机单帧/OCR、无同源音频或时间不连续内容只能保留为 `CANDIDATE_ONLY`。PC 学习任务必须保持独立会话和任务边界。

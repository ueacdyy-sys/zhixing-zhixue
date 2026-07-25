# 智能体模型服务配置

手机应用不会保存第三方 API Key。模型服务由已经 TLS 配对的 PC 网关执行，手机只读取服务状态、提交任务和接收经校验的结果文件。

## 本地模型（Ollama）

```powershell
$env:ZHIXING_AI_PROVIDER = 'local'
$env:ZHIXING_OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:ZHIXING_OLLAMA_MODEL = 'qwen3:8b'
```

## OpenAI 兼容云端模型

```powershell
$env:ZHIXING_AI_PROVIDER = 'openai_compatible'
$env:ZHIXING_OPENAI_BASE_URL = 'https://provider.example/v1'
$env:ZHIXING_OPENAI_API_KEY = '<只在本机进程环境中设置，不写入仓库或手机>'
$env:ZHIXING_OPENAI_MODEL = 'provider-model-name'
```

`ZHIXING_OPENAI_BASE_URL` 必须指向 API 的 `v1` 根路径。网关会调用 `GET /models` 检查连通性，并调用 `POST /chat/completions` 提交学习助手请求。它不会向手机返回 API Key、原始上游报错正文或服务器地址。

## 自动选择

```powershell
$env:ZHIXING_AI_PROVIDER = 'auto'
$env:ZHIXING_AI_CLOUD_FAILURE_FALLBACK_LOCAL = 'true' # 可选；未设置时云端错误不会静默改走本地
```

自动模式优先已完整配置的云端模型。仅当显式开启 `ZHIXING_AI_CLOUD_FAILURE_FALLBACK_LOCAL=true` 且本地模型也完整配置时，云端请求失败才会降级到本地；否则手机会看到结构化失败，不会伪造回答。

# DeepSeek 配置与操作模式

本文记录仓库当前接入机制，不维护平台价格或永久有效的模型名单。模型名称与额度以现用本地配置和当日官方文档为准；早期说明保留在 [历史目录](history/2026-08-20-deepseek-api-guide.md)。

## 配置入口

1. 从 [DeepSeek 模板](../config/llm/deepseek.example.yaml) 复制 `config/llm/deepseek.local.yaml`。
2. 在主配置中设置 `llm.config_path: config/llm/deepseek.local.yaml`。
3. `.env` 保存 `DEEPSEEK_API_KEY`；YAML 的 `api_key_env` 只填写环境变量名。
4. 从项目根目录运行，先用 `--sample --dry-run` 检查本地流程。

配置合并为：内置默认 → 主 YAML → 外置 LLM YAML 覆盖 `llm`；实际请求再按 operation 应用独立模式、输出额度和预算。排查时读取需要的字段，不输出完整私有配置或 `.env`。

## 模式分工

| operation | 模式 | 职责 |
| --- | --- | --- |
| `interest_profile` | 全局默认非思考 | 研究兴趣画像 |
| `email_extraction` | 非思考 | 提取有序论文条目和邮件片段 |
| `abstract_extraction` | 非思考 | 复杂网页摘要定位，必须通过原文匹配 |
| `paper_ranking` | 思考、high | 初筛及补充摘要后的相关性复评 |
| `paper_translation` | 非思考 | 最终中文标题和概述，不修改评级 |

全局 `thinking: disabled` 不代表排序关闭思考。`operation_settings.paper_ranking` 会覆盖全局设置；请求日志记录实际操作、模式和额度，详见 [模式隔离](ranking-thinking-mode.md)。

思考请求不发送 `temperature`；非思考请求不发送 `reasoning_effort`。使用模板中的分操作配置，不把所有调用一起切换为思考。

## 接口与可靠性

- 对话请求由客户端把 `base_url` 拼接为 `/chat/completions`；支持根地址或带 `/v1` 的地址，避免重复拼接路径。
- 联网摘要客户端使用官方 `https://api.deepseek.com/v1/tools/search` 与 `/v1/tools/fetch`，共用密钥环境变量。它有独立的请求次数、并发和等待预算，详见 [来源摘要补充](web-abstract-enrichment.md)。
- JSON 模式要求结构化对象；`finish_reason=length` 不接受部分结果，邮件提取按失败区域递归拆分。
- 可重试临时网络错误、408/429 和部分 5xx；鉴权、余额、证书等错误不靠重复请求解决。
- 分操作 socket 超时与整个逻辑请求预算分别设置。不要仅延长 socket 超时或增加重试掩盖卡顿。
- Search 摘要概述不能当作论文 Abstract；付费查询与模型推理用量分别留在既有指标中。

## 如何判断故障

| 证据 | 排查方向 |
| --- | --- |
| 401/403 | 认证变量是否存在、密钥/权限；不打印密钥 |
| 402 | 平台余额或账户限制 |
| 400/422 | 模型、参数、输出模式是否兼容 |
| 429 | 并发/服务限流；考虑减少 worker |
| timeout/network/5xx | 网络、代理、服务端等待；看同次请求时间线 |
| output_length | 输出预算、条目拆分；不是余额不足证据 |
| HTTP 200 但无完整正文 | 不能认定成功；看后续正文、保活、截止时间 |

存在 HTML 不代表所有 API 任务成功，必须查看核心回退提示。更换 key 必须有认证失败等证据；历史服务中断不代表当前服务故障。

## 官方参考

- [API 文档](https://api-docs.deepseek.com/zh-cn/)
- [思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode)
- [JSON 模式](https://api-docs.deepseek.com/zh-cn/guides/json_mode)
- [模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)
- [错误码](https://api-docs.deepseek.com/quick_start/error_codes/)

修改接入参数前核对官方文档与可用模型；这些链接是参考入口，本次文档整理未重新探测 DeepSeek 服务。

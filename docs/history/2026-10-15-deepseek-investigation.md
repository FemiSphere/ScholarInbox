> 历史记录：参数、测试数量和服务状态仅代表当时。当前维护从 [文档索引](../README.md) 开始。

# DeepSeek 接口与终端调整（2026-10-15）

## 判断

本次故障与 DeepSeek 官方服务中断一致，当前没有更新 API key 的依据。

官方事故页 https://status.deepseek.com/incidents/7116348214287 报告网页/API 部分中断，影响 Flash 和 Pro。起始时间为 2026-10-15 00:11 UTC（北京时间 08:11）；检查时状态为 Identified，正在实施修复。这是当时的状态快照，后续可能恢复。

## 配置核对与实测

| 项目 | 当前配置/实测 | 判断 |
| --- | --- | --- |
| 入口 | https://api.deepseek.com/chat/completions | 与官方 OpenAI 格式相符 |
| 模型 | deepseek-flash | 官方当前名称，认证 /models 返回列表包含此模型 |
| 认证 | Authorization: Bearer，从环境变量取 key | /models 与 /user/balance 均返回 200，无需更换 key |
| 余额 | /user/balance 返回 is_available=true | 当前 key 所属账户余额可用，未输出具体金额 |
| 思考模式 | thinking.type=disabled，reasoning_effort 空值不发送 | 符合官方关闭方式，无冲突 |
| JSON | response_format.type=json_object，任务提示包含 JSON 及示例 | 符合官方要求 |
| 输出额度 | max_tokens=4000 | 合法；较长邮件可能截断，属于另一个效率/完整性问题，不能解释极小请求也不返回 |
| 推理 | 极小流式与非流式请求约 0.2 秒返回 HTTP 200 响应头，随后正文等待超时；另一次非流式观察 35 秒仍未返回正文 | 认证与入口正常，推理正文没有及时返回；与官方事故相符 |
| 最近整批运行 | 11:10 运行全部 8 次 LLM 请求超时 | 新日志确认等待发生于 API，而不是 Gmail 或本地去重 |

对照资料：
- 首次调用与模型名：https://api-docs.deepseek.com/zh-cn/
- 思考模式：https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/
- JSON 模式：https://api-docs.deepseek.com/zh-cn/guides/json_mode/
- 余额接口：https://api-docs.deepseek.com/api/get-user-balance/
- 错误码：https://api-docs.deepseek.com/quick_start/error_codes/
- 保活机制：https://api-docs.deepseek.com/quick_start/rate_limit/

官方说明排队时非流式可能发送空行、流式发送 SSE 保活注释，超过 10 分钟尚未开始推理才关闭连接。HTTP 200 响应头因此不能单独证明推理完成。本次客户端增加响应头与保活日志，继续使用既定总预算，避免无限等待。JSON 解码允许前导空白，不把保活空行当成论文结果。

## 终端调整

- 保留渐变标识；交互终端只保留一个实时阶段/进度条，等待时显示旋转指示与耗时，解析和排序显示完成数。
- API 参数、重试、逐封详情、去重细节、请求指标仅写日志，避免打断进度条。
- 完成时保留论文数量、高/中相关统计、文件路径与日志位置。
- 无交互终端或 --no-color 时只输出阶段变化；--quiet 隐藏进度。
- 直接调用 Python CLI 也自动创建运行日志，不依赖启动脚本。
- API 任务回退时清楚标注临时结果，并跳过本次 Gmail 已读标记与论文索引更新，允许恢复后重跑。此前 11:10 的旧版本已把 20 封邮件标记已读并记录索引；本次未自动恢复这些远端或索引状态。

诊断命令（使用项目 Python）：`python scripts/diagnose_deepseek.py --auth-only` 只验证认证/模型/余额可用性，不调用推理，不输出 key 或金额。省略 --auth-only 会执行两次极小推理请求。

## 验证

101 项测试通过，包含保活 JSON 解析与日志、交互进度、详情仅写日志、API 回退时不写索引及不修改邮件状态。样例 TTY dry-run 已生成 Markdown/HTML，并检查终端记录。没有重跑真实整批邮件，没有更换 key、模型或代理配置。

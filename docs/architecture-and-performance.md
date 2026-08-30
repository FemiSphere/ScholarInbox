# 项目结构与性能分析

本文记录 ScholarPulse 的数据流、历史性能证据、2026-08-21 已实施的优化及其验证边界。历史耗时来自本地 `logs/`；优化后的数字来自离线可复现基准，尚不等同于真实 Gmail 与 DeepSeek 的端到端耗时。

## 1. 当前执行链路

入口是 `literature_digest.cli:main`：

1. 读取 `.env`、主 YAML 和独立 LLM YAML。
2. 从 Gmail 搜索消息列表，以 batch request 分组下载完整 MIME 内容；仍按需单独下载附件。
3. 按发件人、主题和营销关键词过滤邮件。
4. 解析论文条目：
   - Google Scholar 邮件使用本地 HTML/文本规则。
   - 其他期刊、出版社和 RSS 邮件先压缩正文、链接和图片候选，再以最多 3 个 worker 调用 LLM；失败时回退到本地解析器。
5. 按 DOI、URL、规范化标题和模糊标题相似度去重。
6. 查询近 30 天 JSON 论文身份索引，按 DOI、arXiv ID、URL、完全标题和受保护的模糊标题过滤跨日期重复项。
7. 按兴趣文本与模型配置哈希读取或更新研究兴趣画像。
8. 默认每批 20 篇、最多 3 个 worker 调用 LLM，完成相关性、中文标题、摘要和推荐理由；结果按原始批次稳定合并后再按得分排序。
9. 本地生成 Markdown 与 HTML。
10. 非 dry-run 且配置允许时，用 Gmail `batchModify` 分组标记已处理邮件为已读。

解析和排序是前后相继的两个阶段，不会同时占用两组 worker，因此默认最大 LLM 并发为 3，而不是 6。

## 2. 关键模块

| 模块 | 职责 |
| --- | --- |
| `cli.py` | 编排完整工作流、配置性能参数、输出运行指标 |
| `gmail_client.py` | OAuth、Gmail batch、MIME/附件读取、代理与超时 |
| `email_filter.py` | 邮件级过滤 |
| `parsers.py` | 本地解析、prompt 压缩与非 Scholar 有限并发抽取 |
| `dedupe.py` | DOI、URL、标题和模糊标题去重 |
| `paper_registry.py` | 近 30 天 JSON 身份索引、候选分块、原子写入和首次回填 |
| `recent_outputs.py` | 第一次启用 JSON 索引时，从近期 Markdown 恢复历史身份 |
| `interests.py` | 研究兴趣读取、哈希缓存、LLM 提炼和本地回退 |
| `ranking.py` | 可配置批大小与有限并发的排序、翻译和摘要 |
| `telemetry.py` | 线程安全的 LLM/Gmail 请求指标；不保存 prompt 正文 |
| `ui.py` | Rich 启动页、动态进度、终端降级和无 ANSI 运行日志 |
| `digest.py` | Markdown/HTML 渲染和输出命名 |
| `llm/` | Codex CLI、OpenAI-compatible API、退避重试和离线样例客户端 |

## 3. 优化前的本地日志证据

旧日志阶段时间由进度时间戳估算，精度约为 1 秒。

| 日期 | 邮件 | 提取条目 | 总耗时 | Gmail 读取 | 邮件解析 | 兴趣提炼 + 排序摘要 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-08-13 | 9 | 34 | 59 s | 5 s | 11 s | 38 s |
| 2026-08-15 | 23 | 125 | 100 s | 10 s | 3 s | 71 s |
| 2026-08-19 | 64 | 426 | 368 s | 37 s | 45 s | 252 s |
| 2026-08-05 | 51 | 451 | 467 s | 21 s | 92 s | 329 s |

在 8 月 5 日和 8 月 19 日两次大批量运行中，LLM 阶段约占总耗时的 69%–70%。因此优先优化 LLM 编排，比先微调本地解析代码更有价值。

## 4. 已实施的优化

### 4.1 请求级计时与 usage

OpenAI-compatible 和 Codex CLI 请求都会记录用途、条目数、耗时、状态以及是否重试。API 返回 `usage` 时额外记录输入、输出、总 token 和缓存命中 token。日志只保存 prompt 字符数，不保存 prompt 正文、API key 或 OAuth 信息。

终端在运行结束时只保留两行汇总，例如：

```text
LLM metrics: requests=15, retries=1, errors=0, request_time_sum=240.12s, tokens=52340, cache_hit_tokens=1200
Gmail metrics: requests=4, items=101, request_time_sum=9.43s
```

逐 operation 和逐 request 的耗时、token、缓存命中与状态写入 `logs/metrics/metrics-*.log`，不再刷满终端。日志只保存指标，不保存 prompt 正文。`request_time_sum` 是各请求耗时之和；并发时会大于该阶段的墙钟时间，不能把它当作总运行时长。

### 4.2 排序与邮件抽取有限并发

`ranking_max_workers` 和 `parsing_max_workers` 默认均为 3。排序保存批次号并按原始批次合并，因此并发完成顺序不会改变同分论文的稳定顺序。设为 1 可恢复串行行为。

OpenAI-compatible 客户端对 HTTP 429、500、502、503、504 和临时网络错误默认重试 2 次，等待时间按 `1 s、2 s` 指数增长。JSON 不可解析仍保留一次格式纠正重试，两类重试都会进入指标。

### 4.3 研究兴趣画像缓存

缓存键包含：

- `research_interests.md` 的完整文本；
- LLM provider、model、reasoning effort、JSON 输出配置和额外请求参数；
- 缓存格式版本。

默认缓存写入 `data/cache/research_interests.json`，该目录不进入 Git。LLM 提炼失败时使用本地回退画像，但不会把失败结果写入缓存。设置 `refresh_each_run: true` 可强制刷新。

### 4.4 prompt 压缩

非 Scholar 邮件在送入 LLM 前会：

- 去除常见退订、偏好设置、版权和社交页脚；
- 对正文块和候选链接去重；
- 默认限制为 6000 字符正文、50 个链接和 20 个图片候选；
- 对没有候选链接且正文不足 500 字符的低信息邮件直接走本地解析。

这些上限均可在 `performance` 中调整。压缩不改变 Google Scholar 的本地解析路径。

### 4.5 Gmail I/O

完整消息默认每 10 封组成一个 Gmail batch request，单批上限在代码中限制为 100。实测单批 50 个子请求会触发 Gmail per-user concurrent request 限制：50 个请求中曾有 14 个返回 HTTP 429。程序现在只对 429、5xx 和临时网络错误重试失败项，按 `1 s、2 s、4 s` 退避；永久错误仍终止运行并报告 HTTP 状态和原因。标记已读使用 `batchModify`，默认每批最多 1000 个 message ID。附件仍按需单独请求，因为它们只在 MIME part 没有内嵌数据时下载。

Gmail `messages.list` 返回 `resultSizeEstimate` 后，终端显示“符合当前查询条件的未读邮件约 N 封；本次读取 M 封”。前者是 Gmail 提供的估计总数，后者受 `max_emails_per_run` 限制。

dry-run 判断仍在调用已读标记之前；优化没有放宽“不删除邮件”或“不在 dry-run 修改邮件状态”的边界。

### 4.6 近 30 天轻量 JSON 去重索引

跨日期去重不再依赖每次扫描少量 Markdown 文件。程序把最近出现的论文身份保存在 `data/paper_registry.json`，启动时一次读取并建立 DOI、arXiv、URL、完全标题和标题 token 的内存索引。

精确标识使用字典查询；只有精确匹配失败时才从共享标题 token 的小型候选集中执行 RapidFuzz。模糊匹配同时约束标题长度、token Jaccard、数字、化学式和 Part/Comment/Correction 等版本标记，避免 `token_set_ratio` 对包含关系的误判。

索引按 `last_seen` 只保留近 30 天记录。正式运行在 Markdown/HTML 成功写出后原子更新 JSON；sample 和 dry-run 不写入。第一次启用时从近 30 天 Markdown 回填，之后记录所有成功解析的候选论文，而不只记录最终展示的论文。详细规则见 [`deduplication.md`](deduplication.md)。

### 4.7 Rich 交互终端

交互终端显示大尺寸 `ScholarPulse` 标识、“循此苦旅，以抵星辰。”、弱化的作者与包版本，并将逐邮件与逐批次输出收敛为单个动态进度区域。窄终端使用紧凑标题；非 TTY、`--no-color` 和 `NO_COLOR` 环境自动降级。

macOS 启动脚本不再把 Python stdout 直接管道给 `tee`，避免 Rich 误判为非交互环境。`ProgressReporter` 直接写彩色终端，同时把稳定的无 ANSI 文本写入 `logs/digest-*.log`；stderr 仍追加到同一日志。详细请求指标继续单独写入 `logs/metrics/`。

依赖整理后，Rich 是唯一新增的直接 UI 依赖；`markdown-it-py`、`mdurl` 和现有 `Pygments` 由其依赖关系安装。旧代码未使用的 `beautifulsoup4` 与 `python-dotenv` 已从项目声明和专用环境移除。

## 5. 离线基准与批大小判断

可复现命令：

```bash
python scripts/benchmark_performance.py
```

基准使用 240 篇合成论文、固定 `20 ms + 1 ms/篇` 的模拟 LLM 延迟，每组运行 3 次取中位数。它只测编排和等待重叠，不测真实模型吞吐、限流、生成质量或 JSON 截断。

| workers | batch size | 请求数 | 最大实际并发 | 中位耗时 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 12 | 1 | 0.5286 s |
| 2 | 20 | 12 | 2 | 0.2667 s |
| 3 | 20 | 12 | 3 | 0.1792 s |
| 4 | 20 | 12 | 4 | 0.1352 s |
| 3 | 10 | 24 | 3 | 0.2700 s |
| 3 | 30 | 8 | 3 | 0.1626 s |
| 3 | 40 | 6 | 3 | 0.1304 s |

在这个纯延迟模型中，3 worker 相比串行减少约 66% 墙钟时间，4 worker 继续变快。但真实服务存在 429、排队和共享带宽，因此默认选 3，而不是直接选 4。

批次增大在合成基准中更快，但 30–40 篇会扩大单次输出、JSON 截断和整批重试风险。现阶段保留 20 作为保守默认值，并将其改为可配置。应在积累真实 `usage`、重试率和耗时后，再决定是否提高到 25 或 30。

## 6. 验证与剩余瓶颈

当前自动化测试覆盖：有限并发、顺序稳定、缓存失效、prompt 页脚删除、usage/重试指标、Gmail batch、30 天索引清理、DOI/arXiv 别名、模糊误判保护和原子 JSON 写入。验证不调用真实 Gmail 或付费 LLM。

剩余瓶颈主要是：

- 模型生成中文摘要本身的时间，尤其是输出较长时；
- 服务端排队或账号限流；
- 邮件中的独立附件下载；
- 真实邮件模板差异对 prompt 大小和抽取质量的影响。

下一轮真实运行应重点观察 `paper_ranking` 的单请求耗时、429/JSON 重试比例、每批输出 token，以及阶段墙钟时间。若无 429 且批次输出稳定，可小步比较 `ranking_batch_size: 25/30`；若频繁限流，先把 worker 降到 2，而不是扩大重试次数。

DeepSeek 官方参考：[模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[限速与隔离](https://api-docs.deepseek.com/zh-cn/quick_start/rate_limit)、[JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode)。

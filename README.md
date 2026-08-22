# ScholarPulse：把学术提醒邮件整理成中文文献摘要

ScholarPulse 是一个本地 Python 工作流：从专用 Gmail 邮箱读取 Google Scholar alerts、期刊目录、出版社推荐和 RSS 邮件，提取论文条目，去重并调用 LLM 完成中文翻译、摘要和相关性排序，最后生成 Markdown 与 HTML 阅读页。

它的目标不是替代论文精读，而是把分散、重复的学术提醒先整理成一份可以快速筛选的阅读清单。

## 当前能力

- 读取 Gmail 未读邮件；不会删除邮件。
- 解析 Google Scholar 和常见期刊/出版社邮件；非 Scholar 邮件可先由 LLM 做结构化抽取。
- 按 DOI、arXiv ID、规范化 URL 和标题去重，并用轻量 JSON 索引过滤近 30 天已出现的论文。
- 从 `research_interests.md` 提炼近期研究兴趣，据此生成高、中、低相关性和中文推荐理由。
- 支持 Codex CLI 与 OpenAI-compatible API；当前示例包含 DeepSeek 配置。
- 同时输出 Markdown 与 HTML；HTML 支持搜索、相关性筛选、详情折叠和可用的 TOC 图片。
- 支持 dry-run、样例数据、Gmail OAuth 重新授权、可配置代理和不含正文/密钥的请求级性能日志。
- 排序与非 Scholar 抽取使用可配置的有限并发；Gmail 支持批量读取和批量已读标记。

## 工作流

```text
Gmail 学术提醒
  -> 邮件过滤
  -> 论文条目解析
  -> 当前批次去重 + 近 30 天 JSON 身份索引
  -> 读取并提炼近期研究兴趣
  -> LLM 分批排序、翻译和摘要
  -> Markdown + HTML
  -> 可选：成功后标记邮件已读
```

实现边界、关键模块和当前性能分析见 [`docs/architecture-and-performance.md`](docs/architecture-and-performance.md)，跨日期去重规则见 [`docs/deduplication.md`](docs/deduplication.md)。

## 安装

需要 Python 3.10 或更高版本。

```bash
python -m pip install -e ".[dev]"
cp config.example.yaml config.local.yaml
```

Windows PowerShell 可将第二条命令替换为：

```powershell
Copy-Item config.example.yaml config.local.yaml
```

只修改 `config.local.yaml`。本地配置、OAuth 文件、密钥、运行数据、输出和日志均不应提交到 Git。

## Gmail OAuth

1. 在 Google Cloud Console 启用 Gmail API。
2. 创建 Desktop App 类型的 OAuth Client。
3. 下载凭据并命名为 `credentials.json`，放在项目根目录。
4. 第一次读取 Gmail 时，浏览器会打开授权页，成功后生成 `token.json`。

授权失效或更换账号时运行：

```bash
python -m literature_digest --reauth-gmail
```

旧 token 会先备份为 `token.backup-YYYYMMDD-HHMMSS.json`。网络、代理和 macOS/Windows 快捷运行说明见 [`docs/automation-and-shortcuts.md`](docs/automation-and-shortcuts.md)。

## LLM 配置

主配置只引用一个独立的 LLM 配置文件：

```yaml
llm:
  config_path: "config/llm/deepseek.local.yaml"
```

可用模板：

- `config/llm/codex_cli.example.yaml`
- `config/llm/deepseek.example.yaml`

使用 API 时，把真实 key 写入 `.env`，YAML 中只保留环境变量名：

```env
DEEPSEEK_API_KEY=your_api_key
```

DeepSeek 参数和 JSON 输出约束见 [`docs/deepseek-api-guide.md`](docs/deepseek-api-guide.md)。

## 研究兴趣

直接编辑 `research_interests.md`，用自然语言描述当前项目、材料体系、方法、物性和不关心的方向。程序会按兴趣文本和模型配置的哈希缓存结构化画像；只有内容或模型变化，或设置 `refresh_each_run: true` 时才重新调用 LLM。

示例：

```markdown
我近期关注五边形框架材料的理论设计与物性研究，尤其是 COF/MOF/HOF、
机器学习势函数、声子与热输运，以及 AI 辅助材料结构设计。
```

## 跨日期去重

程序使用 `data/paper_registry.json` 保存最近 30 天内见过的论文身份。索引只保存标题别名、DOI、arXiv ID、规范化 URL、来源和日期，不保存邮件正文；`data/` 已被 Git 忽略。

第一次启用时会从近 30 天 Markdown digest 回填。以后在正式运行成功生成输出后，程序会把本次解析出的全部候选论文写入索引，包括因展示数量限制而未出现在 digest 中的条目。sample 和 dry-run 只读取、不写入索引。

详细匹配和保留规则见 [`docs/deduplication.md`](docs/deduplication.md)。

## 运行

先用内置样例验证本地链路；该命令不读取 Gmail，也不需要 LLM API key：

```bash
python -m literature_digest --dry-run --sample
```

离线比较排序并发数和批大小：

```bash
python scripts/benchmark_performance.py
```

再小批量读取真实邮箱：

```bash
python -m literature_digest --dry-run --max-emails 5
```

常用参数：

```text
--config PATH       指定主配置文件
--max-emails N      覆盖单次读取邮件数
--date YYYY-MM-DD   指定输出日期标签
--quiet             隐藏进度信息
--reauth-gmail      强制重新进行 Gmail OAuth
```

正式标记已读必须同时满足：

- `config.local.yaml` 中 `gmail.mark_as_read: true`
- 命令行使用 `--no-dry-run`

项目不会删除邮件。输出写入 `outputs/`，日志写入 `logs/`。

## 一键运行

macOS：

```bash
scripts/run_digest_macos.sh --dry-run --sample
```

Windows：

```text
scripts/run_digest.bat
scripts/run_digest.ps1
```

脚本会从自身位置定位项目根目录，因此仓库移动后通常不需要修改脚本内部路径。

## 测试与提交前检查

```bash
python -m pytest
python -m literature_digest --dry-run --sample
```

确认命令成功，并确认 `outputs/` 中生成了新的 Markdown digest。

## 安全约定

以下文件或目录必须留在本地：

- `.env`
- `config.local.yaml` 及其备份
- `config/llm/*.local.yaml`
- `credentials.json`
- `token.json` 及其备份
- `Gmail_oauth*.md`
- `data/`
- `outputs/`
- `logs/`

错误信息和日志不得打印 API key、OAuth token、refresh token 或邮箱凭据。

## 当前边界

- 邮件格式适配仍是启发式与 LLM 结构化抽取的组合，不保证覆盖所有出版社模板。
- 排序依据标题、来源、邮件片段和可见元数据，不等同于阅读全文后的学术评价。
- LLM 并发默认限制为 3；若服务返回较多 429，可在 `performance` 中降为 2 或 1。实际速度仍受模型生成时间、输出长度和网络影响。
- Gmail 附件仍需按 MIME part 单独下载；批量邮件读取主要减少完整消息请求的往返次数。
- 邮件回发尚未实现；当前完成的是本地 Markdown/HTML 输出和可选的已读标记。

<div align="center">

# ScholarInbox

**把分散的学术提醒邮件，整理成可快速筛选的个性化文献摘要。**

Gmail · Google Scholar · Codex / DeepSeek · Markdown + HTML

[在线示例](https://htmlpreview.github.io/?https://github.com/FemiSphere/ScholarInbox/blob/master/examples/2026-04-30-digest.html) ·
[配置与快捷运行](docs/automation-and-shortcuts.md) ·
[架构与性能](docs/architecture-and-performance.md)

> 循此苦旅，以抵星辰。

</div>

ScholarInbox 是一个面向科研用户的本地 Python 工作流。它从 Gmail 中读取 Google Scholar、
期刊目录和出版社提醒，提取论文信息、去重，并根据研究兴趣完成中文翻译、摘要和相关性排序。

## 核心能力

- 解析 Google Scholar 与常见期刊、出版社提醒邮件。
- 按 DOI、arXiv ID、规范化 URL 和标题去重，并过滤近 30 天重复论文。
- 根据 `research_interests.md` 生成高、中、低相关性及中文推荐理由；非学术内容单列为“不相关”。
- 支持 Codex CLI 与 OpenAI-compatible API，示例包含 DeepSeek 配置。
- 同时生成 Markdown 和可搜索、可筛选的 HTML 阅读页。
- 提供 dry-run、离线样例、Gmail 批处理、可配置代理和纯文本运行日志。

```text
Gmail 学术提醒
  → 邮件过滤与论文提取
  → 当前批次去重 + 近 30 天身份索引
  → 研究兴趣匹配与 LLM 摘要
  → Markdown + HTML
  → 可选：成功后标记邮件已读
```

## 快速开始

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/FemiSphere/ScholarInbox.git
cd ScholarInbox
python -m pip install -e ".[dev]"
cp config.example.yaml config.local.yaml
```

先运行完全离线的样例检查；它不会读取 Gmail，也不会调用在线 LLM：

```bash
python -m literature_digest --dry-run --sample
```

### Gmail OAuth

1. 在 Google Cloud Console 启用 Gmail API。
2. 创建 **Desktop App** 类型的 OAuth Client。
3. 将下载的凭据命名为 `credentials.json`，放入项目根目录。
4. 首次读取 Gmail 时按浏览器提示授权；成功后会生成本地 `token.json`。

授权失效或更换账号时运行：

```bash
python -m literature_digest --reauth-gmail
```

### LLM

在 `config.local.yaml` 中选择 LLM 配置文件：

```yaml
llm:
  config_path: "config/llm/deepseek.local.yaml"
```

可从以下模板开始：

- `config/llm/deepseek.example.yaml`
- `config/llm/codex_cli.example.yaml`

API key 应写入本地 `.env`，不要直接写入可提交的 YAML。DeepSeek 配置说明见
[`docs/deepseek-api-guide.md`](docs/deepseek-api-guide.md)。

## 运行

```bash
# 离线样例
python -m literature_digest --dry-run --sample

# 小批量读取真实邮箱，但不改变邮件状态
python -m literature_digest --dry-run --max-emails 5

# 按本地配置正式运行
python -m literature_digest --no-dry-run
```

只有同时满足以下两个条件，程序才会把成功处理的邮件标记为已读：

- `config.local.yaml` 中设置 `gmail.mark_as_read: true`；
- 命令行使用 `--no-dry-run`。

程序不会删除邮件。结果写入 `outputs/`，日志写入 `logs/`，请求指标写入 `logs/metrics/`。

HTML 阅读页按相关性分区展示结果。“低相关”仍指研究方向之外的正常学术论文；推销、商业宣传、
活动广告以及错误提取内容会进入默认折叠的“不相关”分区。邮件预过滤阶段直接拦截的推广邮件则
继续记录在“跳过的邮件”中，便于检查过滤规则。

## macOS 一键运行

启动脚本会自动定位项目根目录，并依次查找项目 `.venv`、`scholar-inbox-mac` Conda 环境、
兼容的旧环境 `literature-digest-mac` 和系统 Python：

```bash
scripts/run_digest_macos.sh --dry-run --sample
```

如需中文快捷命令，可在 `~/.zshrc` 中加入：

```zsh
alias 文献='/path/to/ScholarInbox/scripts/run_digest_macos.sh'
```

### 仅让 ScholarInbox 使用 Clash

部分网络环境无法直连 Google OAuth 和 Gmail API。先在 Clash 中确认 **HTTP/Mixed** 监听地址，
再在 `~/.zshrc` 中配置 ScholarInbox 专用变量：

```zsh
export SCHOLAR_INBOX_PROXY_URL="http://127.0.0.1:7897"
alias 文献='/path/to/ScholarInbox/scripts/run_digest_macos.sh'
```

`7897` 只是示例；常见端口还有 `7890`，请以自己的 Clash 设置为准。重新打开终端或执行
`source ~/.zshrc` 后，直接运行 `文献` 即可。

这个专用变量不会让整个终端走代理。只有 `run_digest_macos.sh` 会在 ScholarInbox 子进程内
临时设置 HTTP(S) 代理，命令退出后当前 shell 的代理状态不变。无需代理的用户不要设置该变量。

可选的本地绕过地址：

```zsh
export SCHOLAR_INBOX_NO_PROXY="localhost,127.0.0.1,::1"
```

Windows 用户可使用 `scripts/run_digest.bat` 或 `scripts/run_digest.ps1`。更完整的快捷命令、
Conda 环境和自动化说明见 [`docs/automation-and-shortcuts.md`](docs/automation-and-shortcuts.md)。

## 数据与安全

以下内容只应保留在本地，项目已通过 `.gitignore` 排除：

- `.env`、`config.local.yaml`、`config/llm/*.local.yaml`
- `credentials.json`、`token.json` 及其备份
- `data/`、`outputs/`、`logs/`

近 30 天去重索引位于 `data/paper_registry.json`，只保存论文身份信息，不保存邮件正文。
sample 和 dry-run 不写入索引，也不会修改 Gmail 状态。

## 文档

| 文档 | 内容 |
|---|---|
| [配置、快捷运行与自动化](docs/automation-and-shortcuts.md) | macOS、Windows、Conda、代理和计划任务 |
| [架构与性能](docs/architecture-and-performance.md) | 模块边界、并发、批处理、日志与性能 |
| [跨日期去重](docs/deduplication.md) | 论文身份、匹配规则与 30 天索引 |
| [DeepSeek API](docs/deepseek-api-guide.md) | 模型、参数、密钥和结构化输出配置 |

## 开发与验证

```bash
python -m pytest
python -m compileall -q literature_digest
python -m literature_digest --dry-run --sample
```

提交前应确认测试通过，并检查 `outputs/` 中生成的新 Markdown 与 HTML 摘要。

## 当前边界

- 邮件模板解析由规则与 LLM 抽取共同完成，不保证覆盖所有出版社格式。
- 相关性判断基于邮件中的标题、来源、摘要和可见元数据，不等同于论文精读。
- Gmail 和 LLM 的速度、限流与可用性仍取决于外部服务和当前网络环境。

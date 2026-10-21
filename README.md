<div align="center">

# ScholarInbox

**把学术提醒邮件，整理成可快速筛选的个性化文献日报。**

Gmail · Google Scholar / 期刊周报 · DeepSeek / Codex CLI · Markdown + HTML

[在线示例](https://htmlpreview.github.io/?https://github.com/FemiSphere/ScholarInbox/blob/master/examples/2026-04-30-digest.html) · [文档入口](docs/README.md) · [维护地图](docs/code-map.md)

> 循此苦旅，以抵星辰。

</div>

## 工作流程

```text
邮件读取/过滤 → 条目提取/长邮件分块 → 批内与跨日期去重
  → 按研究兴趣初筛 → 可选原始摘要补充与复评
  → 中文标题/概述 → MD + 可搜索、筛选的 HTML
  → 核心成功后，按配置标记邮件已读
```

研究兴趣由 `research_interests.md` 维护。相关性分高、中、低；正常但偏离方向的论文仍属于低相关，推广及非学术条目单列。不等同于全文精读。

DeepSeek 模板仅在相关性分析/复评时开启思考，邮件提取和翻译保持非思考。联网补充仅使用身份匹配的原始摘要，失败保留初筛；页面只增加摘要来源链接。详见 [摘要补充](docs/web-abstract-enrichment.md)。

## 安装与配置

需要 Python 3.10+；使用专用环境。

```bash
git clone https://github.com/FemiSphere/ScholarInbox.git
cd ScholarInbox
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp config.example.yaml config.local.yaml
```

已有安装使用现有项目环境，无需重复安装。当前 Mac 使用 `literature-digest-mac` Conda 环境；Windows 激活方式及启动入口见 [快捷运行](docs/automation-and-shortcuts.md)。

- Gmail：启用 Gmail API，创建 Desktop App OAuth Client，凭据放根目录 `credentials.json`；首次授权后生成 `token.json`。
- DeepSeek：复制 `config/llm/deepseek.example.yaml` 为 `config/llm/deepseek.local.yaml`，主配置设 `llm.config_path` 指向它；密钥写根目录 `.env` 的 `DEEPSEEK_API_KEY`。
- Codex CLI：对应模板为 `config/llm/codex_cli.example.yaml`。
- 真实配置及凭据不进 Git。合并顺序和模式见 [LLM 配置](docs/deepseek-api-guide.md)。

## 运行

从项目根目录执行：

```bash
# 完全离线，不读真实邮箱或调用在线 API
python -m literature_digest --sample --dry-run

# 读取少量真实邮件，可能付费调用 API，但不修改 Gmail 状态/索引
python -m literature_digest --dry-run --max-emails 5

# 正式运行，允许已配置的副作用
python -m literature_digest --no-dry-run
```

只有正式运行、`gmail.mark_as_read: true` 且核心任务无回退，才会标记已处理邮件为已读；不删除邮件。核心任务回退时仍可能生成可读 HTML，但会提示不完整，并保留未读和去重索引状态。可选联网失败保留初筛结果，不按核心失败处理。

日报在 `outputs/`，日志在 `logs/`，请求指标在 `logs/metrics/`，本地索引/缓存/图片在 `data/`。这些目录被 Git 忽略。不要因清理中间文件而删除用户日报、索引、图片和历史诊断证据。

macOS 一键入口：

```bash
scripts/run_digest_macos.sh --sample --dry-run
```

可为该脚本配置 `文献` 别名；`SCHOLAR_INBOX_PROXY_URL` 仅让脚本子进程使用指定代理。配置步骤见 [快捷命令、代理与自动化](docs/automation-and-shortcuts.md)。终端 HTML 路径使用 OSC 8 链接；详细请求信息保留在日志。

## 目录与维护入口

```text
AGENTS.md                代理维护约束（先读）
literature_digest/       Python 源码
config.example.yaml      主配置模板
config/llm/              LLM 模板与被忽略的本地覆盖
tests/                   离线测试
scripts/                 启动、诊断、模拟基准
research_interests.md    用户当前研究兴趣
docs/README.md           按任务选择文档
docs/code-map.md         模块/函数/测试定位
docs/maintenance.md      排障与文件保留规则
docs/history/            历史记录，默认不载入上下文
examples/                公开阅读页示例
```

后续优化先读 `AGENTS.md`，再从代码地图选相关文件；无需重复扫描所有历史日报、日志、数据和文档。完整文档导航见 [docs/README.md](docs/README.md)。

## 验证与边界

在项目环境运行 `python -B -m pytest -q`；编排/渲染变化再跑离线 sample，检查 MD/HTML。纯文档调整只检查链接、代码路径、参数一致性及 diff。

邮件模板、站点访问与 API 可用性仍影响提取和摘要覆盖率。数据不足会保留限定表述；新增摘要及思考模式是否改善推荐准确率，需要人工标注评估。现有缓存与日志的保留规则见 [维护指南](docs/maintenance.md#目录与清理)。

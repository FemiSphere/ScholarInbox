<div align="center">

# ScholarInbox

**把学术提醒邮件，整理成可快速筛选的个性化文献日报。**

Gmail · Google Scholar / 期刊周报 · DeepSeek / OpenAI 兼容接口 / Codex CLI · HTML

[在线示例](https://htmlpreview.github.io/?https://github.com/FemiSphere/ScholarInbox/blob/master/examples/2026-04-30-digest.html) · [English](README.en.md) · [文档入口](docs/README.md)

> 循此苦旅，以抵星辰。

</div>

## 它做什么

```text
读取 Gmail 未读提醒 → 过滤推广邮件 → 提取论文条目（长邮件分块）
  → 批内与近 30 天跨日期去重 → 按你的研究兴趣评级
  → 高/中相关可选联网补充原始摘要并复评 → 中文标题与概述
  → 生成 HTML 日报 → 核心步骤成功后按配置标记已读
```

相关性分五级：

| 级别 | 含义 | 页面中 |
| --- | --- | --- |
| 高相关 / 中相关 | 与当前课题直接相关 / 有可用联系 | 完整卡片 |
| 低相关 | 同一大方向内，但与具体课题联系较弱 | 单行列表，点击展开 |
| 领域外 | 是学术论文，但不属于你的研究大方向 | 默认折叠，仅标题 |
| 不相关 | 推广、活动、错误提取等非学术内容 | 默认折叠 |

HTML 日报支持搜索与筛选、已读/收藏（保存在本机浏览器，跨日报共享）、隐藏已读、导出收藏为 Markdown、图片放大，以及顺滑的展开与滚动动效（遵循系统“减少动态效果”设置）。

## 五步上手

需要 Python 3.12+（推荐 3.13）。

```bash
# 1. 获取代码并安装到独立环境
git clone https://github.com/FemiSphere/ScholarInbox.git
cd ScholarInbox
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

# 2. 交互式初始化：选择模型、写入 API key、生成配置和研究兴趣文件
scholar-inbox init

# 3. 离线自检（不访问 Gmail，不产生费用）
scholar-inbox doctor

# 4. 离线演示
scholar-inbox --sample --dry-run

# 5. 读取少量真实邮件试运行，再正式运行
scholar-inbox --dry-run --max-emails 5
scholar-inbox --no-dry-run
```

`init` 会提示你准备两样东西：

- **Gmail 授权文件**：在 Google Cloud 启用 Gmail API，创建“桌面应用”类型的 OAuth 客户端，下载为项目根目录的 `credentials.json`。首次正式运行会打开浏览器授权并生成 `token.json`。
- **研究兴趣**：编辑 `research_interests.md`（由 [模板](research_interests.example.md) 复制）。用自然语言写，**“大方向”一节决定哪些论文会被折叠为领域外**。

> `python -m literature_digest` 与 `scholar-inbox` 等价；在没有安装入口脚本时可用前者。

## 日常使用

```bash
scholar-inbox --no-dry-run          # 正式运行：生成日报，成功后按配置标为已读
scholar-inbox --dry-run             # 预览：可能调用付费 API，但不修改 Gmail 和去重索引
scholar-inbox --reauth-gmail        # 重新授权 Gmail
```

- 日报在 `outputs/`，终端结尾给出可点击的文件链接，并提示邮箱中还剩多少未读邮件。
- 只有正式运行、`gmail.mark_as_read: true` 且核心步骤无回退时才标记已读；程序从不删除邮件。若核心步骤回退，日报仍会生成并提示不完整，邮件保持未读以便重跑。
- macOS 可用 `scripts/run_digest_macos.sh`（自动定位环境、可设进程级代理）；Windows 用 `scripts/run_digest.bat`。见 [快捷运行与自动化](docs/automation-and-shortcuts.md)。

## 常用配置

`config.local.yaml` 只需写要改的键，全部选项见 [config.example.yaml](config.example.yaml)：

```yaml
llm:
  preset: deepseek            # deepseek（推荐）/ openai_compatible / codex_cli
gmail:
  max_emails_per_run: 50
  mark_as_read: true
digest:
  max_high_relevance: 20      # 各级别展示上限；超出部分会在“运行提示”中说明
  max_medium_relevance: 30
  cleanup_old_outputs: true   # 正式运行后清理 60 天前的日报
filtering:
  mark_skipped_as_read: false # 被判为推广的邮件是否也标为已读
telemetry:
  log_retention_days: 30      # 自动清理 30 天前的运行日志
```

API key 写在项目根目录 `.env`（如 `DEEPSEEK_API_KEY=...`）。模型预设与覆盖方式见 [LLM 配置](docs/llm-configuration.md)。

## 目录

```text
literature_digest/        源码；presets/ 为内置模型预设
tests/                    离线测试
scripts/                  启动脚本（macOS / Windows）、诊断与基准
docs/                     文档（docs/README.md 为入口；history/ 为历史记录）
examples/                 公开示例日报
config.example.yaml       全部配置项参考
research_interests.example.md   研究兴趣模板
```

本地运行产生、已被 Git 忽略的内容：`config.local.yaml`、`research_interests.md`、`.env`、`credentials.json`、`token.json`、`outputs/`（日报）、`logs/`（日志）、`data/`（去重索引、缓存、图片）。

## 开发与维护

```bash
python -B -m pytest -q                         # 全套离线测试
python -B -m literature_digest --sample --dry-run --quiet --no-color
```

维护约定见 [AGENTS.md](AGENTS.md)，模块定位见 [代码地图](docs/code-map.md)，排障见 [维护指南](docs/maintenance.md)。

评级基于标题、邮件片段和可核验的原始摘要，不等同于全文精读；高相关不代表结论已被核验。

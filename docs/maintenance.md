# 维护与排障

改代码先按 [代码地图](code-map.md) 选择模块。纯文档整理无需真实 API；在线诊断与真实邮箱操作分别确认范围，避免把 dry-run 当成完全离线。

## 环境与验证

在项目根目录执行。先激活现有环境：

```bash
conda activate literature-digest-mac
python -B -m pytest -q
python -B -m literature_digest --sample --dry-run --quiet --no-color
```

当前 Mac 专用环境已从 Python 3.11.15 升级为 3.13.18，Google SDK 的旧 Python 支持预警不再通过屏蔽 warnings 处理。项目最低要求为 3.12；`.python-version` 与 `environment.yml` 记录推荐解释器，`requirements.lock` 固定本次验证的依赖。依赖升级应独立评估，不借解释器升级一起无约束更新。

当前 Mac 也可直接使用 `/opt/homebrew/Caskroom/miniforge/base/envs/literature-digest-mac/bin/python`。其他机器按 README 建项目环境，不在 base 临时安装依赖。macOS 启动脚本会定位环境并切到项目根目录。

代码改动先跑相关测试，完成后再全量；渲染/编排变化检查新 MD/HTML。测试产物优先用 `TemporaryDirectory`；需要真实启动时给独立 `--date` 标签，确认后只清理自己产生的测试产物。不要覆盖真实日报。

sample 完全离线；真实 `--dry-run --max-emails N` 会读取 Gmail、可能付费调用 LLM/Search/Fetch，并写本地输出、日志和部分缓存，但不标已读、不保存论文索引。

## 最小排查路径

1. 用文件修改时间选择最新 1–2 个 `logs/digest-*.log`，先看开始/完成、最后阶段和核心回退原因。
2. 对应 `logs/metrics/requests-*.jsonl` 看请求开始/结束、operation、状态与重试；`metrics-*.log` 为结束汇总。以时间线关联同次运行，不能只认相邻文件名。
3. 翻译 `invalid_schema` 先查请求指标中的 `translation_item_recovery`，定位 index、failed_fields 及最终是否恢复；原请求 `status=ok/stop` 不代表字段校验通过。
   每次运行都“跳过”同几封邮件时，看日报底部“跳过的邮件”中的原因：被跳过的邮件默认保持未读，会反复出现。推广关键词按整词匹配，Google Scholar 快讯发件人内置信任；确为推广的邮件可设 `filtering.mark_skipped_as_read: true` 随正式运行一起标为已读。
4. 解析慢看 `email_extraction`、chunk/递归/缓存命中；排序慢看 `paper_ranking`；翻译慢看 `paper_translation`；联网补充看 `evidence_request_*`、`web_*`。
5. 比较墙钟时间、请求重试、输出 token 和预算；并发请求耗时求和可能大于总运行时间。
6. 只读相关模块与定向测试。没有证据时不更换 key、不扩大超时、不关闭科学判断保护。

示例（将文件名替换为已选定的一次运行）：

```bash
rg -n '回退|timeout|output_length|budget|web_|evidence_' logs/digest-指定运行.log
```

核心回退会继续生成可读结果，但不保证条目完整，邮件保留未读且索引不更新。可选联网失败只保留初筛，不触发这项保护。Ctrl+C 退出码 130；整次预算到期为 124。不要为了退出等待线程而连续扩大全局取消的影响范围。

## 配置核验

默认值在 `literature_digest/config.py`；主文件默认 `config.local.yaml`，也可用 `--config`；外置 LLM YAML 相对主配置所在目录解析并覆盖 `llm`。操作设置再覆盖该操作的模式、额度与预算。一般数据/输出相对路径仍以运行工作目录为基准。

模型/超时看实际合并字段与请求日志；不要只读一个模板。`--max-emails` 覆盖读取数量；不要同时传 `--dry-run` 与 `--no-dry-run`；当前代码两者同时出现时以 `--no-dry-run` 为准。Gmail 标已读还需要 `gmail.mark_as_read: true` 且核心任务完整成功。

`scripts/diagnose_deepseek.py --auth-only` 是在线认证/模型/余额探测，不输出 key；省略该参数会执行真实推理请求。它不是日常离线测试的一部分。

## 目录与清理

| 路径 | 用途 | 保留/清理规则 |
| --- | --- | --- |
| `literature_digest/`、`tests/`、`scripts/` | 源码、测试、启动/诊断脚本 | Git 管理；不为美观改导入/入口 |
| `literature_digest/presets/`、`config.example.yaml`、`research_interests.example.md` | 公开预设与模板 | 可提交 |
| `config/llm/*.local.yaml`、`config.local.yaml`、`research_interests.md` | 本地配置与个人研究兴趣 | 已忽略，不提交 |
| `.env`、OAuth 文件、令牌备份 | 私有认证 | 保留原路径，禁止输出正文或自动清除 |
| `research_interests.md` | 用户维护的当前科研兴趣 | 不是缓存；不要自动改写研究方向 |
| `docs/`、`docs/history/` | 当前导航/机制、历史证据 | 按任务读取，不批量载入历史 |
| `examples/` | 公开阅读页示例 | 与私有 outputs 区分 |
| `outputs/` | MD/HTML 日报 | 默认长期保留。开启 `digest.cleanup_old_outputs` 后，正式成功运行仅清理文件名日期早于当天减 60 天的日报，保留本次输出。 |
| `logs/`、`logs/metrics/` | 诊断证据 | 每次非 sample 运行结束后，删除文件名日期早于 `telemetry.log_retention_days`（默认 30）天的 `digest-*.log`、`requests-*.jsonl`、`metrics-*.log`；其他文件不动，0 表示全部保留 |
| `data/paper_registry.json` | 近 30 天去重身份 | 不当作缓存清除；丢失会影响重复处理 |
| `data/cache/email_parsing/` | 成功邮件提取缓存 | 本地私有；当前没有全局容量回收，不宣称自动清完 |
| `data/cache/research_interests.json` | 兴趣画像缓存 | 按内容哈希失效；不等于兴趣源文件 |
| `data/cache/web_evidence.sqlite3` | 来源摘要缓存 | 300 条/8 MiB/30 天，负缓存 6 小时，自动淘汰；停机后可删 |
| `data/cache/results.sqlite3` | 每篇论文的评级与翻译结果（仅成功结果） | 正式运行成功后清空；否则 7 天过期、最多 5000 条（`result_cache.*`）；回退重跑或 dry-run 后正式运行时复用；停机后可删 |
| `data/toc_images/` | 日报图片资源 | 已有 HTML 可能引用，不单独批量删除 |
| `data/config_backups/`、`data/validation/` | 私有备份/历史核验 | 不是程序抓取垃圾；有目的地保留/人工归档。2026-11-25 根目录的旧配置备份、令牌备份与 OAuth 笔记移至 `data/config_backups/root-files-20261125/` |
| `.pytest_cache/`、`__pycache__/` | 可再生成的测试/字节码 | 无运行进程时可清理；不要顺带删未知 `.tmp` 内容 |
| `*.egg-info/` | editable 安装元数据 | 已忽略；不当临时日志删除，可能影响安装元数据查询 |

Search/Fetch 原始页面、清洗内容和搜索响应只存内存，不落逐篇文件。临时 SQLite 事务在异常/取消时关闭；无法识别的数据库不会被自动删除。不要为“目录干净”清掉已有缓存/索引、图片或用户文件。

## 2026-10-27 维护记录

代码起点 `0b7c86c`，修改前标签 `checkpoint-before-python-upgrade-20261027`。升级前 Conda 显式包清单、revision 和 portable pip 版本记录保留在本地 `data/environment_backups/20261027-python313/`；不包含项目 OAuth/API 凭据。Conda revision 只回滚 Conda 包，不能单独还原 pip 包，恢复时须同时使用该目录依赖记录。当前运行仍使用同名 `literature-digest-mac` 环境，base 未修改。

近两次已完成运行：10/26 核验摘要 1/25、Fetch 44/46 返回404；10/27 核验摘要 7/19、Fetch 12/20 返回404，4次arXiv直取全部成功；Search均成功。10/27 一次邮件提取超时已重试恢复，无最终核心回退，不为此继续扩大等待。

本次改为非arXiv优先Search的原始content，再按限制Fetch。任何未恢复的获取失败保留明确错误，不缓存成“没有摘要”；负缓存策略更新，已有成功摘要可复用。并发任务复制调用方上下文以继承预算；后台线程启动失败释放已占用网络名额。此次完成 258 项离线测试、依赖检查及启动脚本 MD/HTML 验证；未重跑真实邮箱/付费 API，不能据此声称获取成功率已进一步提高。

## 文档如何保持简洁

行为变化更新对应专题与代码地图；默认参数在模板维护，不向所有文档重复拷贝。历史实测移入 history，保留日期、范围和限制。AGENTS 只保留全局约束，不记录逐次执行日志、完整 prompt、测试长输出或未启用的模型路由方案。

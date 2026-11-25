# 代码与测试地图

从症状选一行，再读取相关函数；无需先读完整 `cli.py` 或所有测试。下表源码路径相对 `literature_digest/`，测试相对 `tests/`。

| 修改点/症状 | 源码入口 | 相关测试 |
| --- | --- | --- |
| 整体流程、状态保护、数量限制 | `cli.py:main/_main/_apply_digest_limits` | `test_cli_limits.py`、`test_registry_cli.py`、`test_enrichment_pipeline.py` |
| 默认参数/LLM 预设/外置配置覆盖 | `config.py:load_config/_apply_llm_preset/_load_external_llm_config`、`presets/*.yaml`、`llm/factory.py:build_llm_client` | `test_config.py`、`test_operation_settings.py` |
| 首次配置向导、离线自检 | `setup_wizard.py:run_init/run_doctor/collect_checks`（`cli.py:main` 分派 `init`/`doctor`） | `test_setup_wizard.py` |
| Gmail OAuth、读取/代理/附件 | `gmail_client.py:GmailClient` | `test_gmail_client.py` |
| 推广过滤/兴趣画像、跳过邮件标已读 | `email_filter.py:classify_email`、`interests.py`、`cli.py:_main` | `test_filter_and_interests.py`、`test_skipped_mail.py` |
| Scholar/期刊邮件提取、解析缓存 | `parsers.py:parse_emails/_parse_non_scholar_email_with_llm` | `test_parsers.py`、`test_parser_resilience.py` |
| 长邮件边界、图片引用、递归拆分 | `email_chunks.py:build_email_chunks/split_email_chunk` | `test_email_chunks.py`、`test_parser_resilience.py` |
| DOI/URL/标题批内去重 | `dedupe.py` | `test_dedupe.py` |
| 跨日期去重/首次从旧日报回填 | `paper_registry.py`、`recent_outputs.py` | `test_paper_registry.py`、`test_recent_outputs.py`、`test_registry_cli.py` |
| 相关性五级（含领域外）、分析与翻译隔离 | `models.py:RELEVANCE_LEVELS`、`ranking.py:rank_papers/_paper_input/translate_ranked_papers`、`interests.py`（`broad_fields`） | `test_translation_recovery.py`、`test_translation_cli_recovery.py`、`test_ranking_separation.py`、`test_ranking_evidence.py` |
| Search/Fetch、论文身份/摘要核验 | `web_evidence.py:WebEvidenceClient/direct_arxiv/acquire_evidence/extract_abstract` | `test_web_evidence.py` |
| 免费元数据摘要（Crossref/OpenAlex、DOI/PII/标题解析） | `scholarly_sources.py:ScholarlyClient/acquire_from_metadata/titles_match` | `test_scholarly_sources.py` |
| 高/中相关补充、复评与可选失败 | `enrichment.py:enrich_ranked_papers` | `test_enrichment_pipeline.py` |
| SQLite 摘要缓存/容量/过期 | `evidence_cache.py:EvidenceCache` | `test_evidence_cache.py` |
| HTTP 等待、重试、JSON/length、操作模式 | `llm/openai_compatible.py:OpenAICompatibleClient`、`llm/base.py` | `test_api_resilience.py`、`test_api_output_validation.py`、`test_operation_settings.py` |
| Codex CLI 后端/离线 stub | `llm/codex_cli.py`、`llm/offline_stub.py` | `test_performance.py`、`test_ranking_and_digest.py` |
| 并发/取消/阶段预算 | `concurrency.py:cooperative_map`、`llm/base.py:llm_time_budget`、`cli.py:main` | `test_concurrency.py`、`test_api_resilience.py`、`test_enrichment_pipeline.py` |
| HTML/MD、论文详情、图片、来源链接 | `digest.py:write_digests/render_html/_render_paper_card`；页面样式（四套版式 pop/bauhaus/riso/fresh，`digest.theme` 选择默认值）与交互（已读/收藏、导出、版式切换）在 `digest_assets.py` | `test_digest_outputs.py`、`test_ranking_and_digest.py`、`test_ranking_evidence.py` |
| 评级/翻译结果缓存、截断后翻译 | `result_cache.py:ResultCache`、`cli.py:_open_result_cache/_translate_displayed` | `test_result_cache.py` |
| 日志保留期、剩余未读提示 | `housekeeping.py:prune_old_logs`、`cli.py:_prune_logs/_remaining_unread_note` | `test_housekeeping.py` |
| 终端标题（静态）、阶段清单、单行进度、结果摘要、OSC 8、纯文本日志 | `ui.py:ProgressReporter/_header` | `test_ui.py` |
| 请求状态、token/耗时、实时事件 | `telemetry.py:RunMetrics/llm_operation` | `test_live_metrics.py`、`test_performance.py` |

共享类型在 `models.py`：`PaperEntry` 是邮件提取数据；`EvidenceRecord` 是独立核验摘要；`RankedPaper` 组合分析/翻译/证据；`DigestRun` 是渲染输入。不要把联网证据塞进邮件原始字段以免改变解析缓存语义。

配置：`config.example.yaml` 是全部可选项的参考；模型与分操作参数在包内预设 `literature_digest/presets/*.yaml`，由 `llm.preset` 选择。研究兴趣模板为 `research_interests.example.md`。私有文件不在此地图展开。测试公共夹具在 `tests/conftest.py`（清除代理等环境变量）。

环境：`environment.yml`、`.python-version`、`requirements.lock`；详见维护指南。

启动：`__main__.py` → `cli.main`；`pyproject.toml` 注册 `scholar-inbox`、`literature-digest`；`scripts/run_digest_macos.sh` 负责环境定位、进程级代理和日志路径。Windows 入口为同目录的 `.ps1`、`.bat`。

定向搜索与测试示例（先激活项目环境）：

```bash
rg -n 'def acquire_evidence|def extract_abstract' literature_digest/web_evidence.py
python -B -m pytest -q tests/test_web_evidence.py tests/test_enrichment_pipeline.py
```

文件名与函数名便于搜索，不固定容易漂移的行号。新增/移动模块时更新对应行，不复制实现或完整 prompt。

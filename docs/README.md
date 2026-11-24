# 文档入口

只读取任务对应的一行；无需把整个 docs 作为上下文。当前机制以代码与合并后的配置为准，历史测试数量不是当前验收门槛。

| 任务 | 首先读取 | 再按需要读取 |
| --- | --- | --- |
| 安装、日常运行 | [项目说明](../README.md) | [快捷命令/代理/自动化](automation-and-shortcuts.md) |
| 修改代码、定位职责和测试 | [代码与测试地图](code-map.md) | 对应源码与测试 |
| 理解流水线/失败边界 | [当前架构](architecture-and-performance.md) | [数据类型](../literature_digest/models.py) |
| 程序变慢、回退、取消或文件清理 | [维护与排障](maintenance.md) | 同次运行的日志/请求指标 |
| LLM 配置覆盖、思考模式 | [LLM 配置](llm-configuration.md) | [排序与翻译分离](ranking-thinking-mode.md) |
| 周报/期刊目录提取不全、length | [长邮件与截断恢复](long-email-extraction.md) | `email_chunks.py`、`parsers.py` |
| 搜索摘要、复评、缓存 | [来源摘要补充](web-abstract-enrichment.md) | `web_evidence.py`、`enrichment.py`、`evidence_cache.py` |
| 跨日期重复/漏收 | [去重机制](deduplication.md) | `paper_registry.py`、`dedupe.py` |
| 追查过去事件或基准 | [历史目录](history/README.md) | 仅指定日期的记录 |

文档分工：`AGENTS.md` 只写稳定维护约束；本页只做导航；代码地图写入口与测试；专题写机制；历史目录保留当时证据。避免在多份文件重复完整参数表和每次测试数量。

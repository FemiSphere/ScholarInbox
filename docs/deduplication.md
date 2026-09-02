# 跨日期去重设计

ScholarInbox 使用 `data/paper_registry.json` 保存最近 30 天内见过的论文身份。它是普通 JSON 文件，不是数据库；启动时一次载入内存，正式输出成功后原子重写。

## 匹配顺序

1. DOI：从 `doi`、URL、邮件片段和摘要分别提取，统一大小写，并清理出版社页面的 `/meta`、`/pdf`、`/full` 等路由后缀。
2. arXiv ID：忽略 `v1`、`v2` 等版本号，将同一预印本的重复推送视为同一身份。
3. 规范化 URL：删除常见跟踪参数和 fragment。
4. 完全标题：执行 Unicode NFKC、HTML entity、希腊字母、标点和空白规范化。
5. 模糊标题：只比较共享足够信息 token 的候选记录，并检查长度比例、token Jaccard、数字、化学式及版本标记。

模糊标题默认阈值为 94。`Part I/II`、Comment、Reply、Correction、Corrigendum 等标记不同的标题不会自动合并。

## 30 天保留规则

每条记录包含 `first_seen` 和 `last_seen`。加载和保存时，程序删除 `last_seen` 早于参考日期 30 天的记录。

如果同一论文在窗口内再次出现，`last_seen` 会更新，因此仍保留在索引中。这可以持续抑制被多个 Google Scholar 订阅词反复推送的同一论文，同时让长期没有再出现的记录自然退出。

## 写入边界

- 第一次启用且 JSON 不存在时，从近 30 天 Markdown digest 回填。
- 正式运行只有在 Markdown/HTML 成功写出后才更新 JSON。
- 写入先落到 `.tmp` 文件并 `fsync`，再用 `os.replace()` 原子替换。
- sample 和 dry-run 可以读取索引进行模拟，但不写入。
- JSON 记录所有解析出的候选论文，包括未进入最终展示数量范围的低相关条目。
- JSON 不保存邮件正文、摘要或认证信息；整个 `data/` 目录不进入 Git。

## 配置

```yaml
deduplication:
  registry_enabled: true
  registry_path: "data/paper_registry.json"
  retention_days: 30
  fuzzy_title_threshold: 94
  bootstrap_from_outputs: true
```

设置 `registry_enabled: false` 可关闭跨日期 JSON 去重，但当前批次内的 DOI、URL 和标题去重仍然生效。

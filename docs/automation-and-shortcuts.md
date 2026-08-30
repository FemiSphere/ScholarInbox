# 自动化运行与桌面一键运行

本文说明两种运行方式：

- 使用 Codex Automations 或系统计划任务定期运行。
- 在 macOS 终端使用 alias 一键运行，或在 Windows 桌面创建双击即可运行的快捷方式。

## 推荐命令

在项目根目录运行：

```powershell
python -m literature_digest --dry-run --max-emails 50
```

默认 `dry-run` 不会修改 Gmail 状态，也不会标记已读。确认稳定后，如果希望处理过的邮件自动标记为已读，需要同时满足：

- `config.local.yaml` 中 `gmail.mark_as_read: true`
- 运行时使用 `--no-dry-run`

正式运行示例：

```powershell
python -m literature_digest --no-dry-run --max-emails 50
```

项目不会删除邮件。

## Codex Automations 示例

每周一、周三、周五运行：

```text
每周一、周三、周五上午 9:00，在本地项目目录中运行：

python -m literature_digest --dry-run --max-emails 50

运行完成后只告诉我新生成的 md/html 文件路径和统计信息，不需要展开摘要内容。
```

每周运行一次：

```text
每周一上午 9:00，在本地项目目录中运行：

python -m literature_digest --dry-run --max-emails 100

运行完成后报告 outputs 目录中新生成的 digest 文件路径。
```

每隔几天运行一次：

```text
每 3 天上午 9:00，在本地项目目录中运行：

python -m literature_digest --dry-run --max-emails 80
```

## 避免 Codex CLI 中间会话长期保留

如果使用 Codex CLI 后端，可在模型配置中启用 ephemeral 模式：

```yaml
provider: "codex_cli"
timeout_seconds: 120
max_output_tokens: 3000

codex_cli:
  executable: "codex"
  model: "gpt-5.4-mini"
  reasoning_effort: "low"
  ephemeral: true
```

这会让程序调用：

```powershell
codex exec --ephemeral ...
```

如果仍然不希望摘要任务调用 Codex CLI，可改用 OpenAI-compatible 后端，例如 DeepSeek：

```yaml
llm:
  provider: "openai_compatible"
  config_path: "config/llm/deepseek.local.yaml"
```

## Windows 桌面一键运行

仓库提供：

```text
scripts\run_digest.ps1
scripts\run_digest.bat
```

双击 `scripts\run_digest.bat` 会：

- 自动定位项目根目录。
- 设置 Python UTF-8 环境变量。
- 运行 `python -m literature_digest`。
- 将日志保存到 `logs\digest-YYYYMMDD-HHMMSS.log`。

如果中文控制台显示异常，脚本中的固定提示会使用英文输出。

## 创建桌面快捷方式

在 PowerShell 中进入项目根目录后运行：

```powershell
$ProjectRoot = (Get-Location).Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "ScholarPulse.lnk"
$Target = Join-Path $ProjectRoot "scripts\run_digest.bat"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$Shortcut.Save()
```

之后桌面会出现 `ScholarPulse` 快捷方式，双击即可运行。

## 邮件积累较多时的建议

处理速度主要取决于：

- Gmail 下载邮件正文和附件的速度。
- 邮件解析和去重速度。
- LLM 摘要与排序速度。

通常最慢的是 LLM。建议先小批量处理：

```powershell
python -m literature_digest --dry-run --max-emails 20
```

确认效果后再提高到：

```powershell
python -m literature_digest --dry-run --max-emails 50
```

如果一天内多次运行，程序会自动避免覆盖同名输出文件。

## macOS 终端一键运行

macOS 推荐使用独立 conda 环境，避免依赖系统自带 Python，也避免把完整运行环境放在项目目录里：

```zsh
conda create -y -n literature-digest-mac python=3.11 pip
conda run -n literature-digest-mac python -m pip install -e ".[dev]"
```

仓库提供 macOS 启动脚本：

```zsh
scripts/run_digest_macos.sh
```

脚本会：

- 自动定位项目根目录。
- 优先使用项目内 `.venv/bin/python`；如果不存在，则使用 `literature-digest-mac` conda 环境。
- 设置 Python UTF-8 环境变量。
- 将终端运行日志保存到 `logs/digest-YYYYMMDD-HHMMSS.log`。
- 将逐请求耗时和 token 指标保存到 `logs/metrics/metrics-*.log`，终端只显示汇总。
- 如果 shell 中配置了 `CODEX_PROXY_URL`、`CODEX_ALL_PROXY_URL`、`CODEX_NO_PROXY`，自动传给 Python 请求库。

当前用户的 `~/.zshrc` 已写入：

```zsh
alias 文献='/Users/xinyuan/Workbench/My-literature-digest/scripts/run_digest_macos.sh'
```

打开新终端后可直接运行：

```zsh
文献
```

如果暂时无法访问 Google，可先只跑内置样例，验证本地链路：

```zsh
文献 --dry-run --sample
```

小批量真实 Gmail dry-run 命令如下。该命令不会标记邮件已读：

```zsh
文献 --dry-run --max-emails 5
```

如果换电脑、换系统、长时间未使用后 Gmail 授权失效，可以强制重新授权：

```zsh
文献 --reauth-gmail
```

该命令会先把旧的 `token.json` 备份为 `token.backup-YYYYMMDD-HHMMSS.json`，再打开浏览器完成 Google OAuth。重新授权需要当前网络能正常访问 Google。

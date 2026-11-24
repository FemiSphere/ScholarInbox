"""`scholar-inbox init` (guided first-time setup) and `scholar-inbox doctor` (offline self-check).

Both work from the current directory, like the main command. Neither prints secrets,
and `doctor` never calls Gmail or a paid API.
"""
from __future__ import annotations

import getpass
import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import DEFAULT_CONFIG, available_presets, load_config
from .env import load_dotenv_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERESTS_TEMPLATE = PROJECT_ROOT / "research_interests.example.md"

GMAIL_STEPS = """\
  Gmail 授权文件（credentials.json）获取步骤：
    1. 打开 https://console.cloud.google.com/ ，新建（或选择）一个项目；
    2. “API 和服务 → 库”中启用 Gmail API；
    3. “OAuth 同意屏幕”选择“外部”，并把接收提醒的邮箱加为测试用户；
    4. “凭据 → 创建凭据 → OAuth 客户端 ID”，应用类型选“桌面应用”；
    5. 下载 JSON，重命名为 credentials.json 放到项目根目录。
  首次正式运行或执行 `scholar-inbox --reauth-gmail` 时会打开浏览器完成授权并生成 token.json。"""

PROVIDERS = {
    "1": ("deepseek", "DeepSeek（推荐，成本低，支持联网补充原始摘要）"),
    "2": ("openai_compatible", "其他 OpenAI 兼容接口（需填写 base_url 与模型名）"),
    "3": ("codex_cli", "Codex CLI（使用本机已登录的 codex 命令，无需 API key）"),
}


# --------------------------------------------------------------------------- init

def run_init(argv: list[str] | None = None, *, ask: Callable[[str], str] = input,
             ask_secret: Callable[[str], str] = getpass.getpass, base_dir: Path | None = None) -> int:
    base = base_dir or Path.cwd()
    say = print
    say("ScholarInbox 初始化向导（直接回车使用方括号中的默认值）\n")

    config_path = base / "config.local.yaml"
    llm_preset = None
    key_env = None
    if config_path.exists() and _yes(ask(f"已存在 {config_path.name}，保留现有配置？[Y/n] "), default=True):
        say("  保留现有配置。")
        try:
            existing = load_config(config_path)
            provider = existing["llm"].get("provider")
            if provider == "openai_compatible":
                key_env = existing["llm"]["openai_compatible"].get("api_key_env")
        except Exception as exc:  # noqa: BLE001 - only used for a hint
            say(f"  ! 现有配置无法读取：{exc}")
    else:
        say("\n选择模型后端：")
        for number, (_, label) in PROVIDERS.items():
            say(f"  {number}. {label}")
        choice = (ask("请输入序号 [1]: ").strip() or "1")
        llm_preset = PROVIDERS.get(choice, PROVIDERS["1"])[0]
        llm_lines = [f"  preset: {llm_preset}"]
        if llm_preset == "deepseek":
            key_env = "DEEPSEEK_API_KEY"
        elif llm_preset == "openai_compatible":
            base_url = ask("  接口地址 base_url（例如 https://api.example.com/v1）: ").strip()
            model = ask("  模型名称: ").strip()
            key_env = ask("  API key 环境变量名 [OPENAI_API_KEY]: ").strip() or "OPENAI_API_KEY"
            llm_lines += ["  openai_compatible:", f'    base_url: "{base_url}"', f'    model: "{model}"',
                          f'    api_key_env: "{key_env}"']
        max_emails = _int(ask("\n单次最多处理多少封未读邮件？[50]: "), 50)
        mark_read = _yes(ask("正式运行成功后把已处理邮件标为已读？（建议确认流程正常后再开启）[y/N] "), default=False)
        name = ask("终端横幅中显示的名字（可留空）: ").strip()
        content = "\n".join([
            "# 由 scholar-inbox init 生成。完整可选项及说明见 config.example.yaml。",
            "gmail:",
            f"  max_emails_per_run: {max_emails}",
            f"  mark_as_read: {'true' if mark_read else 'false'}",
            "",
            "llm:",
            *llm_lines,
            "",
            "digest:",
            '  output_formats: ["html"]',
            "",
            "ui:",
            f'  display_name: "{name}"',
            "",
        ])
        config_path.write_text(content, encoding="utf-8")
        say(f"  ✓ 已写入 {config_path.name}")

    if key_env:
        _ensure_api_key(base, key_env, ask_secret, say)
    elif llm_preset == "codex_cli" and not shutil.which("codex"):
        say("  ! 未在 PATH 中找到 codex 命令，请先安装并登录 Codex CLI。")

    interests = base / "research_interests.md"
    if interests.exists():
        say("  ✓ 已有 research_interests.md，保留不变。")
    elif INTERESTS_TEMPLATE.exists():
        shutil.copyfile(INTERESTS_TEMPLATE, interests)
        say("  ✓ 已从模板创建 research_interests.md —— 请用自己的研究方向改写它，尤其是“大方向”一节。")

    if (base / "credentials.json").exists():
        say("  ✓ 已找到 credentials.json。")
        if not (base / "token.json").exists():
            say("    首次正式运行时会打开浏览器授权 Gmail；也可现在执行 `scholar-inbox --reauth-gmail`。")
    else:
        say("  ! 还没有 credentials.json。\n" + GMAIL_STEPS)

    say("\n下一步：")
    say("  scholar-inbox doctor                      # 检查配置是否齐全（离线，不产生费用）")
    say("  scholar-inbox --sample --dry-run          # 离线演示，生成示例日报")
    say("  scholar-inbox --dry-run --max-emails 5    # 读取少量真实邮件试运行（会调用模型 API）")
    say("  scholar-inbox --no-dry-run                # 正式运行")
    return 0


def _ensure_api_key(base: Path, key_env: str, ask_secret: Callable[[str], str], say: Callable[[str], None]) -> None:
    env_path = base / ".env"
    load_dotenv_file(env_path)
    if os.environ.get(key_env):
        say(f"  ✓ 已检测到 {key_env}（不显示内容）。")
        return
    secret = ask_secret(f"  请输入 {key_env}（输入不回显，直接回车跳过）: ").strip()
    if not secret:
        say(f"  ! 已跳过。稍后可在 .env 中加入一行：{key_env}=你的 key")
        return
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    lines = [line for line in lines if not line.strip().startswith(f"{key_env}=")]
    lines.append(f"{key_env}={secret}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    os.environ[key_env] = secret
    say(f"  ✓ 已写入 .env（该文件已被 .gitignore 忽略）。")


def _yes(answer: str, *, default: bool) -> bool:
    answer = answer.strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "是", "好", "1", "true"}


def _int(answer: str, default: int) -> int:
    try:
        value = int(answer.strip())
    except ValueError:
        return default
    return value if value > 0 else default


# --------------------------------------------------------------------------- doctor

@dataclass(slots=True)
class Check:
    status: str  # "ok" | "warn" | "fail"
    title: str
    hint: str = ""


_DEPENDENCIES = {
    "googleapiclient": "google-api-python-client", "google_auth_oauthlib": "google-auth-oauthlib",
    "google.auth": "google-auth", "yaml": "PyYAML", "rapidfuzz": "rapidfuzz", "rich": "rich",
    "requests": "requests", "socks": "PySocks",
}


def collect_checks(config_arg: str | None = None, base_dir: Path | None = None) -> list[Check]:
    base = base_dir or Path.cwd()
    checks: list[Check] = []
    version = sys.version_info
    checks.append(Check("ok" if version >= (3, 12) else "fail", f"Python {version.major}.{version.minor}.{version.micro}",
                        "" if version >= (3, 12) else "需要 Python 3.12 及以上"))

    missing = []
    for module, package in _DEPENDENCIES.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    checks.append(Check("fail", "缺少依赖：" + "、".join(missing), "在项目环境中执行 python -m pip install -e .")
                  if missing else Check("ok", "依赖已安装"))

    config_path = Path(config_arg) if config_arg else base / "config.local.yaml"
    load_dotenv_file(base / ".env")
    config = DEFAULT_CONFIG
    if not config_path.exists():
        checks.append(Check("warn", f"未找到 {config_path.name}，将使用内置默认值（Codex CLI）", "执行 scholar-inbox init 生成配置"))
    try:
        config = load_config(config_path if config_path.exists() else None)
        if config_path.exists():
            checks.append(Check("ok", f"配置可读取：{config_path.name}"))
    except Exception as exc:  # noqa: BLE001 - report any config problem
        checks.append(Check("fail", f"配置无法读取：{exc}", f"检查 {config_path.name} 的 YAML 格式；可用预设：{', '.join(available_presets())}"))

    llm = config["llm"]
    provider = llm.get("provider")
    if provider == "openai_compatible":
        settings = llm.get("openai_compatible", {})
        model = settings.get("model") or "（未设置）"
        checks.append(Check("ok" if settings.get("base_url") and settings.get("model") else "fail",
                            f"模型后端：OpenAI 兼容 · {model}",
                            "" if settings.get("base_url") else "在 llm.openai_compatible 下填写 base_url 与 model"))
        key_env = settings.get("api_key_env", "OPENAI_API_KEY")
        checks.append(Check("ok", f"已设置 {key_env}") if os.environ.get(key_env)
                      else Check("fail", f"缺少 API key：{key_env}", f"在项目根目录 .env 中加入 {key_env}=你的 key"))
    elif provider == "codex_cli":
        executable = llm.get("codex_cli", {}).get("executable", "codex")
        checks.append(Check("ok", f"模型后端：Codex CLI · {llm.get('model')}") if shutil.which(executable)
                      else Check("fail", f"找不到 Codex CLI 命令：{executable}", "安装并登录 Codex CLI，或改用 llm.preset: deepseek"))
    else:
        checks.append(Check("fail", f"未知模型后端：{provider}", f"可用预设：{', '.join(available_presets())}"))

    interests = base / config["research_interests"].get("path", "research_interests.md")
    if not interests.exists():
        checks.append(Check("fail", f"缺少研究兴趣文件：{interests.name}", "执行 scholar-inbox init，或复制 research_interests.example.md 后改写"))
    else:
        text = interests.read_text(encoding="utf-8").strip()
        if not text:
            checks.append(Check("fail", f"{interests.name} 为空", "用自然语言写下研究方向"))
        elif "大方向" not in text and "broad field" not in text.lower():
            checks.append(Check("warn", f"{interests.name} 没有“大方向”一节",
                                "建议补充 2–5 个宽泛学科方向，领域外论文的判断会更准确（参考 research_interests.example.md）"))
        else:
            checks.append(Check("ok", f"研究兴趣文件：{interests.name}"))

    gmail = config["gmail"]
    credentials = base / gmail.get("credentials_path", "credentials.json")
    token = base / gmail.get("token_path", "token.json")
    checks.append(Check("ok", "已找到 Gmail credentials.json") if credentials.exists()
                  else Check("fail", "缺少 Gmail credentials.json（离线 --sample 不需要）", GMAIL_STEPS.strip()))
    if credentials.exists():
        checks.append(Check("ok", "已有 Gmail 授权 token") if token.exists()
                      else Check("warn", "尚未授权 Gmail", "首次正式运行会打开浏览器；或执行 scholar-inbox --reauth-gmail"))
    if not gmail.get("mark_as_read", False):
        checks.append(Check("warn", "gmail.mark_as_read 为 false：正式运行后邮件仍保持未读，下次会被再次读取",
                            "确认流程正常后在 config.local.yaml 中设为 true"))

    for name in ("outputs", "logs", "data"):
        directory = base / name
        target = directory if directory.exists() else base
        if not os.access(target, os.W_OK):
            checks.append(Check("fail", f"目录不可写：{target}", "检查文件夹权限"))
    return checks


def run_doctor(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="scholar-inbox doctor", description="离线检查 ScholarInbox 的安装与配置。")
    parser.add_argument("--config", help="配置文件路径，默认 config.local.yaml")
    args = parser.parse_args(argv)
    symbols = {"ok": "✓", "warn": "!", "fail": "✗"}
    checks = collect_checks(args.config)
    print("ScholarInbox 自检（离线，不访问 Gmail 或模型 API）\n")
    for check in checks:
        print(f"  {symbols[check.status]} {check.title}")
        if check.hint and check.status != "ok":
            for line in check.hint.splitlines():
                print(f"      {line.strip()}")
    failures = sum(check.status == "fail" for check in checks)
    warnings = sum(check.status == "warn" for check in checks)
    print()
    if failures:
        print(f"发现 {failures} 个需要处理的问题、{warnings} 条提醒。")
        return 1
    print(f"可以运行了（{warnings} 条提醒）。先试试：scholar-inbox --sample --dry-run")
    return 0

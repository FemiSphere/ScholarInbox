"""Two tiny inference probes; never prints keys, prompts, or response bodies."""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literature_digest.config import load_config
from literature_digest.env import load_dotenv_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load_dotenv_file(root / ".env")
    config = load_config(root / "config.local.yaml")["llm"]
    api = config["openai_compatible"]
    key = os.environ.get(api["api_key_env"])
    if not key:
        raise SystemExit("API key environment variable is missing")
    def probe(route):
        started = time.monotonic()
        body = {"model": api.get("model") or config["model"],
                "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 16}
        body.update(api.get("extra_body", {}))
        request = urllib.request.Request(api["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        proxies = {"https": args.proxy, "http": args.proxy} if route == "proxy" else {}
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler(proxies)).open(request, timeout=args.timeout) as response:
                payload = json.load(response)
                result = {"route": route, "status": response.status,
                    "finish_reason": payload.get("choices", [{}])[0].get("finish_reason")}
        except Exception as exc:
            result = {"route": route, "status": type(exc).__name__, "http_status": getattr(exc, "code", None)}
        result["seconds"] = round(time.monotonic() - started, 2)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(probe, ["proxy", "direct"]):
            print(json.dumps(result))


if __name__ == "__main__":
    main()

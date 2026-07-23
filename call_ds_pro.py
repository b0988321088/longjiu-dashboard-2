#!/usr/bin/env python3
"""call_ds_pro.py — L3 任務：透過 terminal 調用 DS V4 Pro，繞過 delegation 限制"""
import json, os, sys, requests
from pathlib import Path

# 從 hermes .env 讀取 API key
env_path = Path.home() / "AppData/Local/hermes/.env"
api_key = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            api_key = line.split("=", 1)[1].strip()
            break

if not api_key:
    print("❌ 找不到 DEEPSEEK_API_KEY")
    sys.exit(1)

prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()

resp = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    },
    timeout=120,
)

data = resp.json()
if "choices" in data:
    print(data["choices"][0]["message"]["content"])
else:
    print(f"❌ API 錯誤：{data}")

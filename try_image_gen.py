#!/usr/bin/env python3
"""Try multiple free image generation APIs"""
import urllib.request, json, sys, os, time
from pathlib import Path

OUT = Path(__file__).resolve().parent / "anime_violinist.png"
PROMPT = "anime style portrait young boy violinist black suit blue bow tie concert stage warm lighting"

# Try 1: Pollinations (free, no auth)
urls = [
    f"https://image.pollinations.ai/prompt/{urllib.parse.quote(PROMPT)}?width=768&height=768&nofeed=true&seed=42",
]

try:
    import urllib.parse
    url = urls[0]
    print(f"Trying: {url[:60]}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
        if len(data) > 1000:
            OUT.write_bytes(data)
            print(f"✅ 成功！({len(data)} bytes)")
            print(f"📁 {OUT}")
            sys.exit(0)
        else:
            print(f"❌ 檔案太小: {len(data)} bytes")
except Exception as e:
    print(f"❌ {e}")
    sys.exit(1)

import json, os
env_path = os.path.expanduser("~/Desktop/longjiu_system/.env")
key = None
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY"):
            key = line.split("=", 1)[1].strip("\"'")
            break
if not key:
    print("❌ 找不到 API key")
    exit(1)

import urllib.request
req = urllib.request.Request("https://api.deepseek.com/user/balance",
    headers={"Authorization": f"Bearer {key}"})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"💰 DeepSeek 餘額: {data}")

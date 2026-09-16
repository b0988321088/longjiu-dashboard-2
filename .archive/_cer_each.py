#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐條測試：哪一則訊息的內容會觸發 DeepSeek CER 400"""
import sqlite3, os, json, urllib.request, urllib.error

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, "AppData/Local/hermes/state.db")
SID = "20260915_192539_bbecec5a"
key = [l.split("=", 1)[1].strip() for l in open(os.path.join(HOME, "AppData/Local/hermes/.env"), encoding="utf-8")
       if l.startswith("DEEPSEEK_API_KEY")][0]

c = sqlite3.connect(DB)
rows = list(c.execute("select id,role,tool_name,content from messages where session_id=? and active=1 order by id", (SID,)))


def ask(messages):
    body = {"model": "deepseek-v4-flash", "messages": messages, "max_tokens": 8, "stream": False}
    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return "200"
    except urllib.error.HTTPError as e:
        return "%s %s" % (e.code, e.read(200).decode("utf-8", "replace")[:120])
    except Exception as e:
        return "ERR " + str(e)[:100]


# 每則 tool 訊息單獨測（塞成 user 訊息）
for i, (_id, role, tn, content) in enumerate(rows):
    if role != "tool" or not content or len(content) < 50:
        continue
    res = ask([{"role": "user", "content": content}])
    flag = "FAIL" if res.startswith("400") else "ok  "
    print("%s idx=%-3d id=%s %-12s len=%-6d %s" % (flag, i, _id, tn, len(content), res[:90] if flag == "FAIL" else ""))

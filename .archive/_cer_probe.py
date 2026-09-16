#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CER 400 診斷：用 system_prompts + messages 重放，找出觸發 DeepSeek Content Exists Risk 的內容。"""
import sqlite3, json, os, sys, urllib.request, urllib.error

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, "AppData/Local/hermes/state.db")
SID = "20260915_192539_bbecec5a"

key = None
for line in open(os.path.join(HOME, "AppData/Local/hermes/.env"), encoding="utf-8"):
    if line.startswith("DEEPSEEK_API_KEY"):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")

c = sqlite3.connect(DB)
sess = c.execute("select system_prompt_hash from sessions where id=?", (SID,)).fetchone()
sp_hash = sess[0]
sp = c.execute("select prompt from system_prompts where hash=?", (sp_hash,)).fetchone()
sys_prompt = sp[0] if sp else ""
print("system prompt chars:", len(sys_prompt))

rows = list(c.execute(
    "select id,role,tool_name,content,tool_call_id,tool_calls,token_count from messages "
    "where session_id=? and active=1 order by id", (SID,)))
print("active messages:", len(rows))


def build(rows):
    out = []
    for _id, role, tool_name, content, tcid, tcs, _tk in rows:
        m = {"role": role}
        if role == "tool":
            m["content"] = content or ""
            if tcid:
                m["tool_call_id"] = tcid
        elif role == "assistant":
            m["content"] = content or ""
            if tcs:
                try:
                    m["tool_calls"] = json.loads(tcs)
                except Exception:
                    pass
        else:
            m["content"] = content or ""
        out.append(m)
    return out


def ask(messages, sys_text, max_tokens=8):
    body = {"model": "deepseek-v4-flash",
            "messages": ([{"role": "system", "content": sys_text}] if sys_text else []) + messages,
            "max_tokens": max_tokens, "stream": False}
    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return "200"
    except urllib.error.HTTPError as e:
        return "%s %s" % (e.code, e.read(300).decode("utf-8", "replace"))
    except Exception as e:
        return "ERR " + str(e)[:150]


mode = sys.argv[1] if len(sys.argv) > 1 else "sys"

if mode == "sys":
    # 1) 只有 system prompt + 一句話
    print("A) sys_prompt + 'hi':", ask([{"role": "user", "content": "hi"}], sys_prompt))
    # 2) 沒有 system prompt，全部 active 訊息
    print("B) 無 sys + 全部 active:", ask(build(rows), ""))
    # 3) 完整（sys + 全部）
    print("C) sys + 全部 active:", ask(build(rows), sys_prompt))
elif mode == "bisect":
    def fails(k):
        res = ask(build(rows[:k]), "")
        return res.startswith("400"), res[:60]
    lo, hi = 1, len(rows)
    f, r = fails(hi)
    if not f:
        print("full prefix OK ->", r)
        sys.exit(0)
    print("full(%d) fails" % hi)
    while lo < hi:
        mid = (lo + hi) // 2
        f, r = fails(mid)
        print("prefix %d -> %s" % (mid, "FAIL" if f else "ok"))
        if f:
            hi = mid
        else:
            lo = mid + 1
    print("=== 最小觸發索引:", lo)
    for i in range(max(0, lo - 2), min(len(rows), lo + 1)):
        _id, role, tool_name, content, tcid, tcs, tk = rows[i]
        print("--- idx", i, "id", _id, role, tool_name, "len", len(content or ""), "tok", tk)
        print((content or "")[:400].replace("\n", " "))

else:
    print("usage: cer_probe.py [sys|bisect]")

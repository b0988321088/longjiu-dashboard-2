#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""檢視 active 訊息：content vs api_content"""
import sqlite3, os, json, sys

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, "AppData/Local/hermes/state.db")
SID = "20260915_192539_bbecec5a"
c = sqlite3.connect(DB)
rows = list(c.execute(
    "select id,role,tool_name,content,api_content,tool_calls,display_kind,compacted,active,timestamp "
    "from messages where session_id=? order by id", (SID,)))
act = [r for r in rows if r[8] == 1]
print("rows", len(rows), "active", len(act))
for i, r in enumerate(act[:14]):
    _id, role, tn, content, api, tcs, dk, cmp_, a, ts = r
    print("=== idx", i, "id", _id, role, tn, "| content", len(content or ""), "| api", len(api or ""), "| tk", (tcs or "")[:60], "| dk", dk)
    print("  C:", (content or "")[:120].replace("\n", " "))
    if api and api != content:
        print("  A:", (api or "")[:120].replace("\n", " "))

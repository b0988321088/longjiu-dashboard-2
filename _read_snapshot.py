#!/usr/bin/env python3
import json, os

os.chdir(r'C:\Users\bot\Desktop\龍九系統')

print("=== SNAPSHOT ===")
with open('snapshot.json', 'r', encoding='utf-8') as f:
    snap = json.load(f)

print(f"Top-level keys: {list(snap.keys())}")
for k, v in snap.items():
    if isinstance(v, dict):
        print(f"\n--- {k} ({type(v).__name__}, {len(v)} keys) ---")
        # Print first few sub-keys
        sub_keys = list(v.keys())[:10]
        for sk in sub_keys:
            sv = v[sk]
            if isinstance(sv, (int, float)):
                print(f"  {sk}: {sv}")
            elif isinstance(sv, str):
                print(f"  {sk}: {sv[:100]}")
            elif isinstance(sv, list):
                print(f"  {sk}: list[{len(sv)}]")
            elif isinstance(sv, dict):
                print(f"  {sk}: dict[{len(sv)}]")
    elif isinstance(v, list):
        print(f"\n--- {k} (list, {len(v)} items) ---")
        if v:
            print(f"  First item: {json.dumps(v[0], ensure_ascii=False)[:200]}")
    elif isinstance(v, (int, float)):
        print(f"\n--- {k}: {v}")
    elif isinstance(v, str):
        print(f"\n--- {k}: {v[:200]}")
    else:
        print(f"\n--- {k}: {type(v).__name__}")

print("\n\n=== DECISIONS ===")
with open('dashboard_decisions.json', 'r', encoding='utf-8') as f:
    dec = json.load(f)

print(f"Type: {type(dec).__name__}")
if isinstance(dec, dict):
    print(f"Top-level keys: {list(dec.keys())[:20]}")
    for k, v in dec.items():
        if isinstance(v, list):
            print(f"\n--- {k}: list[{len(v)}]")
            if v:
                print(f"  First: {json.dumps(v[0], ensure_ascii=False)[:300]}")
        elif isinstance(v, dict):
            print(f"\n--- {k}: dict[{len(v)}] keys={list(v.keys())[:10]}")
        elif isinstance(v, str):
            print(f"\n--- {k}: {v[:200]}")
        elif isinstance(v, (int, float)):
            print(f"\n--- {k}: {v}")
elif isinstance(dec, list):
    print(f"list of {len(dec)} items")
    if dec:
        print(f"First item: {json.dumps(dec[0], ensure_ascii=False)[:300]}")
        if len(dec) > 1:
            print(f"Last item: {json.dumps(dec[-1], ensure_ascii=False)[:300]}")

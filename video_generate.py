#!/usr/bin/env python3
"""AI 影片生成工具 — 呼叫 FAL Kling Video API"""
import json, sys, time, requests
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"
CHAR_FILE = BASE / "video_character_18yo_violinist.json"

def get_fal_key():
    """讀取 FAL_KEY"""
    import os
    k = os.environ.get("FAL_KEY", "")
    if k:
        return k
    try:
        with open(ENV) as f:
            for line in f:
                if "FAL_KEY" in line and "=" in line and "#" not in line.strip()[0]:
                    return line.split("=", 1)[1].strip().strip('"')
    except:
        pass
    return ""

def load_character():
    """載入主角設定"""
    try:
        return json.loads(CHAR_FILE.read_text(encoding="utf-8"))
    except:
        return None

def generate_video(prompt, seconds=5, model="fal-ai/kling-video/v1.6/standard/text-to-video"):
    """呼叫 FAL Kling 生成影片"""
    key = get_fal_key()
    if not key:
        return {"error": "FAL_KEY 未設定，請在 .env 設定或 export FAL_KEY=..."}
    
    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "duration": seconds,
        "fps": 24,
        "cfg_scale": 0.7,
    }
    
    print(f"🎬 正在生成影片...（{seconds}秒）")
    print(f"   Prompt: {prompt[:80]}...")
    
    try:
        r = requests.post(f"https://fal.run/{model}", json=payload, headers=headers, timeout=30)
        if r.status_code == 200:
            result = r.json()
            video_url = result.get("video", {}).get("url") or result.get("output", {}).get("video_url", "")
            if video_url:
                print(f"✅ 影片生成成功！")
                print(f"   {video_url}")
                return {"url": video_url, "prompt": prompt}
            return {"error": "無影片 URL", "raw": result}
        else:
            return {"error": f"HTTP {r.status_code}", "raw": r.text[:200]}
    except Exception as e:
        return {"error": str(e)}

def generate_all_scenes(character_file=None):
    """依主角設定生成所有場景"""
    char = load_character()
    if not char:
        return {"error": "角色設定檔不存在"}
    
    templates = char.get("英文提示詞模板", {})
    char_template = templates.get("角色模板", "Anime style, 18-year-old male violinist, {場景描述}")
    scenes = templates.get("核心場景", [])
    
    results = []
    for scene_name, scene_desc in [
        ("後台緊張", templates.get("後台", "")),
        ("舞台演奏", templates.get("演奏", "")),
        ("評審反應", templates.get("評審反應", "")),
        ("全場歡呼", templates.get("歡呼", "")),
    ]:
        prompt = char_template.replace("{場景描述}", scene_desc)
        result = generate_video(prompt, seconds=5)
        results.append({"scene": scene_name, "prompt": prompt, "result": result})
    
    return results

if __name__ == "__main__":
    if "--setup" in sys.argv:
        print("🎬 影片生成工具準備中...")
        print(f"   角色設定: {CHAR_FILE}")
        print(f"   請先設定 FAL_KEY 環境變數或寫入 .env")
        print(f"   格式: FAL_KEY=your-fal-api-key-here")
    elif "--character" in sys.argv:
        char = load_character()
        if char:
            print(json.dumps(char, ensure_ascii=False, indent=2))
        else:
            print("❌ 角色設定檔不存在")
    else:
        # 單一 prompt 生成
        prompt = " ".join(sys.argv[1:]) or "Anime style, 18-year-old male violinist playing violin on stage"
        result = generate_video(prompt)
        print(json.dumps(result, ensure_ascii=False, indent=2))

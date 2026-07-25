"""記憶寫入共用工具 — 供所有腳本呼叫，寫入 dashboard_decisions.json 再由 memory_sync.py 同步到 holographic"""
import json
from datetime import datetime
from pathlib import Path

def add_memory(agent: str, task: str, summary: str, status: str = "completed"):
    """寫入一條記憶/決策到 dashboard_decisions.json
    
    用法: from memory_helper import add_memory
          add_memory("Hermes", "日報產出", "證券2,479,320 配息118,296")
    """
    path = Path(__file__).resolve().parent / "dashboard_decisions.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except:
        data = {"decisions": [], "meta": {"version": 1}}
    
    entry = {
        "id": f"mem-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(data['decisions'])}",
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "task": task,
        "summary": summary,
        "status": status,
        "source": "auto"
    }
    data.setdefault("decisions", []).append(entry)
    data.setdefault("meta", {})["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  🧠 記憶已寫入: [{agent}] {task}")
    return entry["id"]

if __name__ == "__main__":
    # 測試
    add_memory("Hermes", "測試", "記憶寫入工具測試")
    print("✅ memory_helper 測試完成")

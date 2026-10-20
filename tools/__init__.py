"""龍九 repo 內的 tools 套件標記（2026-10-21）。

存在理由：本目錄原本是 namespace package（無 __init__.py）。Hermes cron 在 Windows
以 uv venv 啟動腳本時，會把 hermes-agent 根目錄放進 PYTHONPATH，而該根目錄下有
另一個「正規套件」tools/（有 __init__.py），匯入解析時正規套件會壓過 sys.path 中更
前面的 namespace 目錄 → `from tools.publish_gate import ...`（regenerate_report.py
L930）解析到 hermes-agent/tools 而 ModuleNotFoundError。

本檔只做套件標記，刻意保持零副作用：不 import 任何模組、不註冊任何東西、不改任何
判定邏輯。目錄內的模組仍以「插入 tools/ 到 sys.path 後直接 import 模組名」的既有方式
使用，不受影響。
"""

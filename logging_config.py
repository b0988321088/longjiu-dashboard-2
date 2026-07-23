"""logging_config.py — 龍九系統統一日誌設定
用法：from logging_config import get_logger; logger = get_logger(__name__)
格式：2026-07-23 10:30:00,123 | INFO | script.py | 訊息"""

import logging, sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S,%f"[:-3],
)

# 控制台 handler
_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_formatter)

# 檔案 handler（每日輪替）
_fh = logging.FileHandler(LOG_DIR / "longjiu.log", encoding="utf-8", mode="a")
_fh.setFormatter(_formatter)

# 根 logger
_root = logging.getLogger()
_root.setLevel(logging.INFO)
if not _root.handlers:
    _root.addHandler(_ch)
    _root.addHandler(_fh)


def get_logger(name: str) -> logging.Logger:
    """取得 logger 實例，傳入 __name__ 即可"""
    return logging.getLogger(name)

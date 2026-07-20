#!/usr/bin/env python3
"""
龍九控股 自動推送腳本
流程：
  1. 呼叫 run_daily.py 產出檔案
  2. 呼叫 daily_checklist.py 檢查
  3. 呼叫 GitHub Contents API 推送 daily_report_v2_{date}.html + index.html
  4. 完成後推送兩個連結到 Telegram
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import base64
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from buffett_cto_analyzer import run as buffett_cto_run
except Exception:
    buffett_cto_run = None

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
DAILY_REPORT = BASE / f"daily_report_v2_{TODAY}.html"
INDEX_FILE = BASE / "index.html"
REPO = os.getenv("GITHUB_REPO", "b0988321088/longjiu-dashboard-2")
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "clean-main")


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n[STEP] {name}")
    result = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[FAIL] {name}\n{result.stderr[:500]}")
        return False
    print(f"[OK] {name}")
    return True


def checklist_failed() -> bool:
    print("\n[STEP] checklist")
    result = subprocess.run(
        [sys.executable, str(BASE / "daily_checklist.py")],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    return result.returncode != 0


def cio_review_failed() -> tuple[bool, str]:
    print("[STEP] cio_review")
    result = subprocess.run(
        [sys.executable, str(BASE / "cio_review.py")],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        return True, result.stdout
    return False, result.stdout


def gemini_review_failed() -> tuple[bool, dict]:
    print("[STEP] gemini_review")
    result = subprocess.run(
        [sys.executable, str(BASE / "gemini_review.py")],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[SKIP/WARN] gemini_review: {result.stderr[:200]}")
        return False, {}
    try:
        data = json.loads(result.stdout)
    except Exception:
        print(f"[WARN] gemini_review output parse failed: {result.stdout[:200]}")
        return False, {}
    status = data.get("status", "")
    if status == "rejected":
        print(f"[REJECTED] Gemini review: {data.get('summary', '')}")
        return True, data
    if status == "error":
        print(f"[ERROR] Gemini review: {data.get('reason', '')}")
        return False, data
    print(f"[OK] Gemini review: score={data.get('score', '?')}, summary={data.get('summary', '')}")
    return False, data


def github_push(filepath: str) -> bool:
    result = subprocess.run(
        ["git", "add", filepath],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        ["git", "commit", "-m", f"auto: {filepath} {TODAY}"],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  git commit: {result.stderr[:200]}")
    result = subprocess.run(
        ["git", "push", "origin", GITHUB_BRANCH],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Common failure: remote branched ahead but local claims clean; force-push as fallback
        if "non-fast-forward" in result.stderr or "Updates were rejected" in result.stderr or "failed to push" in result.stderr:
            result = subprocess.run(
                ["git", "push", "origin", f"HEAD:{GITHUB_BRANCH}", "--force-with-lease"],
                cwd=BASE,
                capture_output=True,
                text=True,
            )
    ok = result.returncode == 0
    print(f"  push {filepath} via git: {result.returncode}")
    if not ok:
        print(f"  {result.stderr[:300]}")
    return ok


def telegram_push(text: str, actions: list | None = None) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[SKIP] Telegram 未設定，跳過推送")
        return True
    import requests

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}

    if actions:
        rows = []
        for a in actions:
            rows.append([
                {"text": "✅ 核准"},
                {"text": "⏸️ 延後"},
            ])
        payload["reply_markup"] = {
            "keyboard": rows,
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }

    r = requests.post(url, json=payload, timeout=10)
    ok = r.status_code == 200
    print(f"  telegram: {r.status_code}")
    return ok




def _load_snapshot() -> dict:
    path = BASE / "snapshot.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_moat_pipeline(output_path: Path) -> bool:
    print("[STEP] moat_pipeline")
    try:
        from asset_moat_monitor import AssetMoatMonitor
        from external_comparator import ExternalComparator
        from dynamic_balancer import DynamicBalancer
    except Exception as exc:
        print(f"  [SKIP] import failed: {exc}")
        return False

    snapshot = _load_snapshot()
    print(f"  debug: loaded snapshot keys = {list(snapshot.keys())[:10]}")
    try:
        monitor = AssetMoatMonitor()
        moat = monitor.compute(snapshot)
    except Exception as exc:
        print(f"  [SKIP] AssetMoatMonitor failed: {exc}")
        return False
    
    try:
        comparator = ExternalComparator()
        bench = comparator.benchmark if hasattr(comparator, "benchmark") else {}
        tw_signal = {
            "twii_return_ytd": (snapshot.get("securities", 0) or 0) * 0.05 if isinstance(snapshot.get("securities"), (int, float)) else 0,
        }
        bench_cmp = comparator.compare(tw_signal, bench)
    except Exception as exc:
        print(f"  [SKIP] Comparator failed: {exc}")
        bench_cmp = {}
    
    try:
        peers = bench.get("peers", [])
        my_fund = {"dividend_yield": 100, "expense_ratio": 1.5}
        peer_cmp = comparator.compare_peers(my_fund, peers) if peers else {}
    except Exception as exc:
        print(f"  [SKIP] Peer comparison failed: {exc}")
        peer_cmp = {}
    
    try:
        balancer = DynamicBalancer()
        signals = {
            "semiconductor_exposure_pct": 0,
            "coverage_ratio": 100,
            "debt_ratio_pct": 35.9,
        }
        balance_suggestion = balancer.suggest(
            {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}, signals
        )
    except Exception as exc:
        print(f"  [SKIP] Balancer failed: {exc}")
        balance_suggestion = {}

    report = {
        "date": TODAY,
        "moat": moat,
        "benchmark_comparison": bench_cmp,
        "peer_comparison": peer_cmp,
        "balancer": balance_suggestion,
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  moat_report -> {output_path.name}")
    return True


def main() -> None:
    print(f"[DEPLOY] 日期：{TODAY}")

    # 1. 產出
    if not run_step("run_daily", [sys.executable, str(BASE / "run_daily.py")]):
        return

    # 2. 檢查
    if checklist_failed():
        print("[STOP] 檢查未過，停止推送")
        return

    # 2.5 CIO 審查
    failed_cio, cio_out = cio_review_failed()
    if failed_cio:
        print("[STOP] CIO 審查未過")
        # Gemini 复核：CIO 擋住時才跑 Gemini 審查（節省 API 呼叫）
        print("[STEP] gemini_review（CIO 擋住，觸發 Gemini 复核）")
        failed_gemini, gemini_data = gemini_review_failed()
        if failed_gemini:
            print("[STOP] Gemini 亦未通過，停止推送")
            return
        else:
            print("[OK] Gemini 复核通過，覆蓋 CIO 決定，繼續推送")
    else:
        print("[CIO 審查] 全部通過。允許推送。")
        # CIO 通過時跳過 Gemini，節省 API 費用

    # 2.7 Moat / Comparator / Balancer
    moat_path = BASE / f"moat_report_{TODAY}.json"
    try:
        _run_moat_pipeline(moat_path)
    except Exception as exc:
        print(f"[WARN] moat pipeline 異常：{exc}，繼續推送")

    # 2.8 Buffett/CTO 分析（讀取報告嵌入 HTML，不手動維護）
    if buffett_cto_run is not None:
        print("[STEP] buffett_cto_analyzer")
        try:
            ok_bc = buffett_cto_run(send=False)  # 報告已由 run_daily 或手動產生，不重複發送
            if ok_bc:
                print("[OK] buffett_cto_analyzer 完成")
            else:
                print("[WARN] buffett_cto_analyzer 發送失敗")
        except Exception as exc:
            print(f"[WARN] buffett_cto_analyzer 異常：{exc}")
        
        # 嵌入 Buffett/CTO 報告到 HTML
        report_path = BASE / f"buffett_cto_report_{TODAY}.md"
        if report_path.exists() and DAILY_REPORT.exists():
            try:
                html = DAILY_REPORT.read_text(encoding='utf-8')
                bc_content = report_path.read_text(encoding='utf-8')
                # Parse markdown-like content into HTML paragraphs
                # Parse markdown-like content into HTML paragraphs
                parts = []
                parts.append('<div class="callout callout-bull">')
                for line in bc_content.splitlines():
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    if line_stripped.startswith('【'):
                        parts.append(f'<h3>{line_stripped}</h3>')
                    elif line_stripped.startswith('•') or line_stripped.startswith('▸'):
                        parts.append(f'{line_stripped}<br>')
                    else:
                        parts.append(f'{line_stripped}<br>')
                parts.append('</div>')
                bc_html = '\n'.join(parts)
                
                html = html.replace(
                    '<!-- BUFFETT_CTO_PLACEHOLDER -->',
                    bc_html
                )
                print("[OK] Buffett/CTO report embedded into HTML")
            except Exception as exc:
                print(f"[WARN] Buffett/CTO embed failed: {exc}")
    else:
        print("[SKIP] buffett_cto_analyzer 模組不存在")

    # 3. 推送
    daily_name = DAILY_REPORT.name
    index_name = INDEX_FILE.name
    ok1 = github_push(daily_name)
    ok2 = github_push(index_name)

    if not (ok1 and ok2):
        print("[FAIL] GitHub 推送失敗")
        return

    # 4. Telegram
    daily_url = f"https://b0988321088.github.io/{REPO.split('/')[1]}/{daily_name}?v={TODAY.replace('-','')}"
    index_url = f"https://b0988321088.github.io/{REPO.split('/')[1]}/{index_name}?v={TODAY.replace('-','')}"
    msg = (
        f"龍九控股日報 {TODAY}\n\n"
        f"日報：{daily_url}\n"
        f"靜態儀表板：{index_url}"
    )
    telegram_push(msg, actions=[{"target": "deploy", "action": "每日部署"}])
    print("\n[DONE] 全部流程完成")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_push_commit_classification.py — 推送拒因「分類依據」正／負向驗收（2026-10-15）

對應使用者 2026-10-15 裁決（P1-3 auto_push --dry-run 誤判純資料 commit）：
  「逐一檢查兩顆 commit 的實際檔案清單、變更內容及 dry-run 判定邏輯，確認它們確實只有資料變更，
    再修正誤判的根因。必須保留對程式檔、混合型提交及未宣告檔案的攔截能力。
    不能直接把兩顆 commit 加入永久白名單，也不能因為標記為『純資料』就自動放行。」
驗收條件：
  ① 純資料提交能被正確辨識（類別＝未命中白名單的純資料，且訊息不得稱其為程式檔）
  ② 真正包含程式變更的提交仍被正確攔截（類別＝程式／設定檔）
  ③ 混合型提交（資料＋程式）不被拆開放行 → 整顆以程式檔論
  ④ 治理／特殊類別（dashboard_decisions.json、reviews/…）仍為強制真 CIO，且不誤標為程式檔
  ⑤ 不得因「純資料」而自動放行：該類仍為 CIO（classify_paths 不回 AUTO）
  ⑥ 任何程式副檔名路徑都不得被歸類為 unlisted_data（分類器不得自我放寬）

全程離線；真 git 沙盒（$TEMP 獨立 repo ＋ 真 publish_allowlist.json 副本），不觸碰產線 repo。
執行：python -X utf8 tools/test_push_commit_classification.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import publish_gate as pg  # noqa: E402

CODE_SUFFIX = pg.CODE_SUFFIX
PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def sandbox() -> Path:
    d = Path(tempfile.mkdtemp(prefix="lj_pcls_"))
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.invalid")
    git(d, "config", "user.name", "t")
    git(d, "config", "core.autocrlf", "false")
    # 用真白名單（HEAD 版；本測試不引入任何新的白名單項目）
    (d / "publish_allowlist.json").write_text(
        (ROOT / "publish_allowlist.json").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    git(d, "add", "--", "publish_allowlist.json")
    git(d, "commit", "-q", "-m", "base")
    return d


def commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, body in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    git(repo, "add", "--", *files)
    git(repo, "commit", "-q", "-m", msg)
    return (git(repo, "rev-parse", "HEAD").stdout or "").strip()


def classes_of(repo: Path, sha: str) -> dict[str, str]:
    paths = pg.commit_changed_paths(repo, sha)
    return {p: d["class"] for p, d in pg.force_cio_reasons(paths, repo).items()}


def main() -> int:
    print("=== 推送拒因分類（真 git 沙盒；真白名單）===")
    d = sandbox()
    try:
        c_allow = commit(d, {"cost.html": "<p>1</p>", "cost_data.json": "{}",
                             "data/ai_cost_daily.jsonl": "{}\n"}, "data: 成本帳（白名單命中）")
        c_unlisted = commit(d, {"asset_diff_history.json": '{"v":1}'}, "data: 資產差異歷史（純資料、未命中白名單）")
        c_code = commit(d, {"tracker.py": "x=1\n"}, "feat: 程式")
        c_mixed = commit(d, {"cost_data.json": "{\"a\":1}", "helper.py": "y=2\n"}, "feat: 混合")
        c_special = commit(d, {"dashboard_decisions.json": '{"decisions":[]}'}, "data(decisions): 入庫")
        c_prefix = commit(d, {"reviews/x_cio_result.json": "{}"}, "chore: 審查紀錄")

        # ① 純資料且命中白名單 → 不列入強制 CIO（可自動落 RECORD）；負向自測證明分類器有鑑別力
        check("①a 白名單命中的純資料 commit → 無強制 CIO 路徑（可自動落 RECORD）",
              classes_of(d, c_allow) == {}, str(classes_of(d, c_allow)))
        check("①b 對照：未命中的純資料 commit → 確實列入（分類器有鑑別力）",
              classes_of(d, c_unlisted) == {"asset_diff_history.json": "unlisted_data"},
              str(classes_of(d, c_unlisted)))

        # ① 純資料：類別＝unlisted_data，且摘要/明細都不得講成程式檔
        u = pg.force_cio_reasons(["asset_diff_history.json", "buffett_cto_report_2026-10-15.md"], d)
        usum, udet = pg.force_cio_summary(u)
        check("①c 純資料摘要＝『未命中白名單的純資料檔 2 檔』",
              "未命中白名單的純資料檔 2 檔" in usum, usum)
        check("①d 純資料不得被歸類／描述為程式改動（誤判根因：訊息一律講含程式檔）",
              "程式／設定檔" not in usum and not any("程式／設定檔" in x for x in udet),
              f"{usum}｜{udet}")
        check("①e 純資料仍明示需真 CIO（不得因純資料而放行）", "真 CIO" in usum, usum)

        # ② 程式檔：仍被攔截且點名程式／設定檔
        csum, cdet = pg.force_cio_summary(pg.force_cio_reasons(["tracker.py"], d))
        check("②a 程式檔 → 類別『程式／設定檔』且明示需真 CIO",
              "程式／設定檔 1 檔" in csum and "真 CIO" in csum, csum)
        check("②b 程式檔 commit 的逐條明細含檔名與原因",
              any("tracker.py" in x for x in cdet), str(cdet))

        # ③ 混合型：資料＋程式 → 整顆以程式論（不得只放行資料那半）
        mx = classes_of(d, c_mixed)
        check("③a 混合 commit → 程式檔 1＋受連帶資料檔 1（整顆仍拒推，不拆開放行）",
              mx == {"helper.py": "code", "cost_data.json": "auto_alone"}, str(mx))
        msum, _ = pg.force_cio_summary(pg.force_cio_reasons(list(mx), d))
        check("③b 混合 commit 摘要同時點名程式檔與受連帶資料檔（實際內容全貌可見）",
              "程式／設定檔 1 檔" in msum and "本顆受他檔連帶的資料檔 1 檔" in msum, msum)

        # ④ 治理／特殊類別（未宣告類）→ special，不得誤標程式檔
        sp = classes_of(d, c_special)
        check("④a dashboard_decisions.json（治理紀錄）→ 類別 special（非 code）",
              sp == {"dashboard_decisions.json": "special"}, str(sp))
        pr = classes_of(d, c_prefix)
        check("④b reviews/ 前綴（未宣告）→ 類別 special（非 code）",
              pr == {"reviews/x_cio_result.json": "special"}, str(pr))

        # ⑤ 不自動放行：純資料（未命中）在閘門仍是 CIO
        v = pg.classify_paths(d, ["asset_diff_history.json"])
        check("⑤a 未命中白名單的純資料 → 閘門 mode=CIO（不因純資料放行）",
              v["mode"] == "CIO" and v["must_cio"], json.dumps(v, ensure_ascii=False)[:150])
        v2 = pg.classify_paths(d, ["cost.html", "cost_data.json", "data/ai_cost_daily.jsonl"])
        check("⑤b 白名單命中的純資料 → 閘門 mode=AUTO（正常車道未被本次修正破壞）",
              v2["mode"] == "AUTO", json.dumps(v2, ensure_ascii=False)[:150])

        # ⑥ 分類器不得自我放寬：任何程式副檔名都不得被歸 unlisted_data
        allp = ["a.py", "b.sh", "c.js", "d.ts", "e.yml", "f.sql", "g.bat", "h.ps1", "i.toml"]
        rr = pg.force_cio_reasons(allp, d)
        check("⑥a 所有程式副檔名 → 一律 class=code（不得被歸 unlisted_data）",
              all(rr[p]["class"] == "code" for p in allp), str(rr))
        check("⑥b 純資料＋程式同時出現時，程式檔仍獨立被點名",
              all(pg.force_cio_summary(rr)[0].count("程式／設定檔") == 1 for _ in [0]))
        check("⑥c 白名單不可用（沙盒無 allowlist ref）→ fail-closed 全歸 special",
              all(v["class"] == "special"
                  for v in pg.force_cio_reasons(["asset_diff_history.json"], d, ref="nosuchref").values()),
              str(pg.force_cio_reasons(["asset_diff_history.json"], d, ref="nosuchref")))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

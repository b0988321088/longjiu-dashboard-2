# -*- coding: utf-8 -*-
"""F1 第一階段測試：staging_handoff 契約／失敗碼 H01–H10／六態／歸檔／公開文字。

驗收邊界（2026-10-20 使用者裁決）：
  - 只在 %TEMP% 沙箱執行；正式 repo 必須零寫入（T00 以 git status 前後比對證明）。
  - 不觸碰正式發布流程：本檔只 import staging_handoff，不呼叫 regenerate／auto_push。
用法：python tools/test_emergency_handoff.py
"""
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

TMP = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "f1_phase1"
SANDBOX = TMP / "staging"
DATE = "2026-10-20"
GEN_OK = f"{DATE}T21:34:00+08:00"

import staging_handoff as sh  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  PASS " if ok else "  FAIL ") + name + ("｜" + str(detail) if detail else ""))


def repo_status():
    r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def reset(tag):
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX, ignore_errors=True)
    d = sh.day_dir(DATE, SANDBOX)
    d.mkdir(parents=True, exist_ok=True)
    os.environ["LJ_HANDOFF_ROOT"] = str(SANDBOX)
    os.environ.pop("LJ_EMERGENCY_HANDOFF", None)
    return d


def put(d: Path, name="analysis.json", payload=None):
    if payload is None:
        payload = {"generated_at": GEN_OK, "full_report": "x" * 2000, "source": "美股開盤"}
    raw = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    (d / name).write_bytes(raw)
    return raw


def seed_valid(d: Path, gen=GEN_OK):
    put(d, "analysis.json", {"generated_at": gen, "full_report": "x" * 2000, "source": "美股開盤"})
    put(d, f"emergency_report_{DATE}.html", "<html>rail</html>")
    put(d, f"emergency_taiex_report_{DATE}.html", "<html>gh</html>")


def sealed(date=DATE, lane=sh.LANE_DEFAULT, gen=GEN_OK, root=None):
    """正常封存（測試用）；回傳 manifest。"""
    seed_valid(sh.day_dir(date, root or SANDBOX), gen=gen)
    r = sh.seal(date, lane=lane, root_dir=root or SANDBOX)
    return r


def handwrite_manifest(date, mutate, root=None):
    """寫入一個「自洽封存」的交接單（seal 紀錄與檔案內容一致），用來隔離單一失敗碼。"""
    root = root or SANDBOX
    d = sh.day_dir(date, root)
    seed_valid(d)
    names = [p.format(date=date) for p in sh.REQUIRED]
    m = {
        "schema": sh.SCHEMA,
        "date": date,
        "lane": sh.LANE_DEFAULT,
        "generated_at": GEN_OK,
        "batch_complete": True,
        "files": [{"name": n, "sha256": sha_bytes((d / n).read_bytes()), "bytes": (d / n).stat().st_size}
                  for n in names],
    }
    mutate(m)
    raw = sh._manifest_bytes(m)
    (d / sh.MANIFEST_NAME).write_bytes(raw)
    sh.mark_status(date, "seal", manifest_sha256=sha_bytes(raw), root_dir=root)
    return raw


def t00_repo_untouched(before):
    after = repo_status()
    check("T00 正式 repo 零寫入（git status 前後一致）", before == after,
          "diff" if before != after else "identical")
    check("T00 staging 根目錄不在 repo 內", not str(sh.root()).lower().startswith(str(REPO).lower()),
          str(sh.root()))


def t01_valid():
    print("\n[T01] 正常交接 → VALID")
    reset("t01")
    r = sealed()
    res = sh.verify(DATE, SANDBOX)
    check("seal 回 VALID", r.state == sh.VALID, r.state)
    check("verify VALID", res.state == sh.VALID, (res.state, res.codes))
    check("三件套齊全", len(res.manifest["files"]) == 3, [f["name"] for f in res.manifest["files"]])
    check("analysis 可讀", (res.analysis or {}).get("full_report", "").startswith("x"), "")
    check("rc=0", res.rc == 0, res.rc)


def t02_tampered_json():
    print("\n[T02] 交接後 analysis.json 被改 → H06")
    reset("t02")
    sealed()
    p = sh.day_dir(DATE, SANDBOX) / "analysis.json"
    b = p.read_bytes()
    i = b.find(b"x")                      # 同長度改一個字元：只觸發 H06，不牽連 H07
    p.write_bytes(b[:i] + b"y" + b[i + 1:])
    res = sh.verify(DATE, SANDBOX)
    check("state=INVALID", res.state == sh.INVALID, res.state)
    check("含 H06", "H06" in res.codes, res.codes)
    check("rc=12", res.rc == 12, res.rc)
    check("public 只含對照表文字", res.public() == "應變資料驗證失敗（H06）", res.public())
    check("public 不含檔名", "analysis.json" not in res.public(), res.public())


def t03_missing_file():
    print("\n[T03] 少一份 HTML → H05")
    reset("t03")
    sealed()
    (sh.day_dir(DATE, SANDBOX) / f"emergency_report_{DATE}.html").unlink()
    res = sh.verify(DATE, SANDBOX)
    check("含 H05", "H05" in res.codes, res.codes)
    check("state=INVALID", res.state == sh.INVALID, res.state)


def t04_no_manifest():
    print("\n[T04] 有目錄無交接單 → H01（不得判 ABSENT）")
    reset("t04")
    seed_valid(sh.day_dir(DATE, SANDBOX))
    res = sh.verify(DATE, SANDBOX)
    check("state=INVALID（非 ABSENT）", res.state == sh.INVALID, res.state)
    check("含 H01", "H01" in res.codes, res.codes)


def t05_absent():
    print("\n[T05] 目錄不存在 → ABSENT")
    reset("t05")
    shutil.rmtree(SANDBOX)
    res = sh.verify(DATE, SANDBOX)
    check("state=ABSENT", res.state == sh.ABSENT, res.state)
    check("rc=0", res.rc == 0, res.rc)
    check("無 codes", res.codes == [], res.codes)


def t06_date_mismatch():
    print("\n[T06] 交接單日期不一致 → H03")
    reset("t06")
    d = sh.day_dir(DATE, SANDBOX)
    seed_valid(d)
    names = [p.format(date=DATE) for p in sh.REQUIRED]
    raw = sh._manifest_bytes({
        "schema": sh.SCHEMA, "date": "2026-10-19", "lane": sh.LANE_DEFAULT, "generated_at": GEN_OK,
        "batch_complete": True,
        "files": [{"name": n, "sha256": sha_bytes((d / n).read_bytes()), "bytes": (d / n).stat().st_size}
                  for n in names]})
    (d / sh.MANIFEST_NAME).write_bytes(raw)
    sh.mark_status(DATE, "seal", manifest_sha256=sha_bytes(raw), root_dir=SANDBOX)
    res = sh.verify(DATE, SANDBOX)
    check("含 H03", "H03" in res.codes, res.codes)
    check("state=INVALID", res.state == sh.INVALID, res.state)


def t07_out_of_window():
    print("\n[T07] generated_at 時窗外 → H04")
    reset("t07")
    handwrite_manifest(DATE, lambda m: m.update({"generated_at": f"{DATE}T08:00:00+08:00"}))
    res = sh.verify(DATE, SANDBOX)
    check("含 H04", "H04" in res.codes, res.codes)


def t08_extra_files():
    print("\n[T08] 契約外檔案：stage 拒絕；目錄多檔不影響驗證")
    reset("t08")
    sealed()
    d = sh.day_dir(DATE, SANDBOX)
    (d / "notes.txt").write_text("scratch", encoding="utf-8")
    res = sh.verify(DATE, SANDBOX)
    check("多餘檔案不影響 VALID", res.state == sh.VALID, (res.state, res.codes))
    check("manifest 僅登錄 3 檔", [f["name"] for f in res.manifest["files"]] ==
          sorted(p.format(date=DATE) for p in sh.REQUIRED), res.manifest["files"])
    try:
        sh.stage(DATE, {"../evil.json": "x"}, root_dir=SANDBOX)
        ok = False
    except ValueError:
        ok = True
    check("stage 拒絕契約外／越界檔名", ok, "")


def t09_schema():
    print("\n[T09] schema／必要欄位不符 → H02")
    reset("t09")
    handwrite_manifest(DATE, lambda m: m.update({"schema": 2}))
    res = sh.verify(DATE, SANDBOX)
    check("schema 不符 → H02", "H02" in res.codes, res.codes)
    reset("t09b")
    handwrite_manifest(DATE, lambda m: m.pop("lane", None))
    res2 = sh.verify(DATE, SANDBOX)
    check("缺 lane → H02", "H02" in res2.codes, res2.codes)


def t10_empty_file():
    print("\n[T10] 空檔 → H07")
    reset("t10")
    sealed()
    (sh.day_dir(DATE, SANDBOX) / f"emergency_taiex_report_{DATE}.html").write_bytes(b"")
    res = sh.verify(DATE, SANDBOX)
    check("含 H07", "H07" in res.codes, res.codes)


def t11_lane():
    print("\n[T11] lane 不在白名單 → H08")
    reset("t11")
    r = sealed(lane="some_other_lane")
    check("seal 即拒絕（不寫交接單）", r.state == sh.INVALID and "H08" in r.codes, (r.state, r.codes))
    check("未留下交接單（fail-closed）", not (sh.day_dir(DATE, SANDBOX) / sh.MANIFEST_NAME).exists(), "")
    reset("t11b")
    handwrite_manifest(DATE, lambda m: m.update({"lane": "unknown_lane"}))
    res = sh.verify(DATE, SANDBOX)
    check("verify 亦擋 H08", "H08" in res.codes, res.codes)


def t12_duplicate_batch():
    print("\n[T12] 同日已發布又出現不同交接單 → H09")
    reset("t12")
    sealed()
    sh.mark_published(DATE, commit="deadbeef", root_dir=SANDBOX)
    d = sh.day_dir(DATE, SANDBOX)
    put(d, "analysis.json", {"generated_at": GEN_OK, "full_report": "z" * 2000})
    names = [p.format(date=DATE) for p in sh.REQUIRED]
    raw = sh._manifest_bytes({
        "schema": sh.SCHEMA, "date": DATE, "lane": sh.LANE_DEFAULT, "generated_at": GEN_OK,
        "batch_complete": True,
        "files": [{"name": n, "sha256": sha_bytes((d / n).read_bytes()), "bytes": (d / n).stat().st_size}
                  for n in names]})
    (d / sh.MANIFEST_NAME).write_bytes(raw)
    sh.mark_status(DATE, "seal", manifest_sha256=sha_bytes(raw), root_dir=SANDBOX)
    res = sh.verify(DATE, SANDBOX)
    check("含 H09", "H09" in res.codes, res.codes)


def t13_manifest_tampered():
    print("\n[T13] 交接單事後被改（封存紀錄不符）→ H10")
    reset("t13")
    sealed()
    d = sh.day_dir(DATE, SANDBOX)
    m = json.loads((d / sh.MANIFEST_NAME).read_text(encoding="utf-8"))
    m["batch_complete"] = True
    m["sealed_at"] = "2026-10-20T23:58:00"      # 事後改內容
    (d / sh.MANIFEST_NAME).write_bytes(sh._manifest_bytes(m))
    res = sh.verify(DATE, SANDBOX)
    check("含 H10", "H10" in res.codes, res.codes)


def t14_disabled_with_data():
    print("\n[T14] flag=off 但有當日資料 → DISABLED_WITH_DATA（rc=13，禁止回退）")
    reset("t14")
    sealed()
    os.environ["LJ_EMERGENCY_HANDOFF"] = "off"
    res = sh.consume(DATE, SANDBOX)
    check("state=DISABLED_WITH_DATA", res.state == sh.DISABLED_WITH_DATA, res.state)
    check("rc=13", res.rc == 13, res.rc)
    check("含 H90", res.codes == ["H90"], res.codes)
    check("不提供 analysis（不得改用 repo 舊 JSON）", res.analysis is None, res.analysis)
    check("public 為對照表文字", res.public() == sh.PUBLIC_TEXT["H90"], res.public())


def t15_dry_run():
    print("\n[T15] dry-run：驗證通過 rc=0 不注入；驗證失敗 rc=0 但留痕")
    reset("t15")
    sealed()
    os.environ["LJ_EMERGENCY_HANDOFF"] = "dry-run"
    res = sh.consume(DATE, SANDBOX)
    check("VALID_DRYRUN", res.state == sh.VALID_DRYRUN, res.state)
    check("rc=0", res.rc == 0, res.rc)
    check("不注入 analysis", res.analysis is None, res.analysis)
    check("狀態留痕 validated_dry_run",
          any(r.get("action") == "validated_dry_run" for r in sh.status_log(DATE, SANDBOX)), "")
    reset("t15b")
    sealed()
    put(sh.day_dir(DATE, SANDBOX), "analysis.json", {"generated_at": GEN_OK, "full_report": "q"})
    os.environ["LJ_EMERGENCY_HANDOFF"] = "dry-run"
    res2 = sh.consume(DATE, SANDBOX)
    check("INVALID_DRYRUN（rc=0 不阻擋）", res2.state == sh.INVALID_DRYRUN and res2.rc == 0,
          (res2.state, res2.rc))


def t16_archive():
    print("\n[T16] 歸檔：published 滿 30 天搬、pending 不搬")
    reset("t16")
    old, recent, pend = "2026-09-01", "2026-10-19", "2026-09-05"
    for dt, act in ((old, "published"), (recent, "published"), (pend, "pending")):
        d = sh.day_dir(dt, SANDBOX)
        d.mkdir(parents=True, exist_ok=True)
        seed_valid(d, gen=f"{dt}T21:34:00+08:00")
        sh.mark_status(dt, act, published_at=f"{dt}T07:05:00+08:00", commit="abc123", root_dir=SANDBOX)
    moved, skipped = sh.archive(now=_dt.datetime.fromisoformat("2026-10-20T12:00:00"), root_dir=SANDBOX)
    check("舊 published 已歸檔", old in moved, moved)
    check("未滿 30 天不搬", any(k[0] == recent for k in skipped) and recent not in moved, skipped)
    check("pending 不搬（不因逾期自動移動）", any(k[0] == pend for k in skipped), skipped)
    dest = SANDBOX / sh.ARCHIVE_DIRNAME / "2026-09" / old
    check("歸檔目的地存在且原目錄消失", dest.is_dir() and not sh.day_dir(old, SANDBOX).exists(), str(dest))
    check("未直接刪除（檔案仍在）", any(dest.iterdir()), "")


def t17_public_text():
    print("\n[T17a] PUBLIC_TEXT：上限 3 筆、僅對照表文字、不洩漏內部細節")
    txt = sh.public_text(["H01", "H05", "H06", "H07", "H10"])
    check("超過 3 筆加註其他項", "及其他 2 項" in txt, txt)
    check("未知碼降級 H99", sh.public_text(["H77"]).endswith("（H99）"), sh.public_text(["H77"]))
    bad = ["analysis.json", "C:", "/", "\\", "staging_handoff", "e3b0c442"]
    joined = sh.public_text(list(sh.PUBLIC_TEXT))
    check("公開文字不含檔名／路徑／元件／sha", not any(b in joined for b in bad), joined)
    check("公開文字不重複同碼", sh.public_text(["H06", "H06"]).count("H06") == 1, sh.public_text(["H06", "H06"]))


def t18_dry_run_verdict():
    print("\n[T18] dry-run 語意：rc=0 不得被當成通過／可啟用")
    reset("t18")
    sealed()
    os.environ["LJ_EMERGENCY_HANDOFF"] = "dry-run"
    ok_res = sh.consume(DATE, SANDBOX)
    check("通過時 verdict=DRYRUN", ok_res.verdict() == "DRYRUN", ok_res.verdict())
    check("通過時 verified=True 但 can_inject=False",
          ok_res.verified() and not ok_res.can_inject(), (ok_res.verified(), ok_res.can_inject()))

    reset("t18b")
    sealed()
    p = sh.day_dir(DATE, SANDBOX) / "analysis.json"
    b = p.read_bytes()
    i = b.find(b"x")
    p.write_bytes(b[:i] + b"y" + b[i + 1:])
    os.environ["LJ_EMERGENCY_HANDOFF"] = "dry-run"
    bad = sh.consume(DATE, SANDBOX)
    log = sh.status_log(DATE, SANDBOX)
    check("失敗時 verdict=DRYRUN_FAIL（不是 PASS／DRYRUN）",
          bad.verdict() == "DRYRUN_FAIL", bad.verdict())
    check("失敗時 verified=False", bad.verified() is False, bad.verified())
    check("失敗時 can_inject=False 且 analysis=None",
          (not bad.can_inject()) and bad.analysis is None, (bad.can_inject(), bad.analysis))
    check("rc=0（不阻擋）但狀態仍為失敗", bad.rc == 0, bad.rc)
    check("留下 invalid_dry_run 紀錄",
          any(r.get("action") == "invalid_dry_run" and r.get("codes") for r in log),
          [r.get("action") for r in log])
    check("未被記成 validated_dry_run",
          not any(r.get("action") == "validated_dry_run" for r in log),
          [r.get("action") for r in log])
    check("未產生 published 紀錄",
          not any(r.get("action") == "published" for r in log), [r.get("action") for r in log])

    reset("t18c")
    sealed()
    os.environ["LJ_EMERGENCY_HANDOFF"] = "on"
    good = sh.consume(DATE, SANDBOX)
    check("on 通過：verdict=PASS、can_inject=True",
          good.verdict() == "PASS" and good.can_inject(), (good.verdict(), good.can_inject()))


def t19_stage_boundary():
    print("\n[T19] stage 邊界：路徑／穿越一律拒絕，且不寫出 staging")
    reset("t19")
    bad_names = ["../evil.json", "sub/analysis.json", "sub\\analysis.json", "C:\\abs.json",
                 "..", ".", "/etc/passwd", "analysis.json.bak"]
    for n in bad_names:
        try:
            sh.stage(DATE, {n: "x"}, root_dir=SANDBOX)
            ok = False
        except ValueError:
            ok = True
        check(f"拒絕 {n!r}", ok, "")
    d = sh.day_dir(DATE, SANDBOX)
    check("越界嘗試未在 staging 內留下任何檔（除既有的）",
          sorted(x.name for x in d.iterdir()) == [], sorted(x.name for x in d.iterdir()))
    outside = (SANDBOX.parent / "evil.json")
    check("未寫到 staging 外的父目錄", not outside.exists(), str(outside))
    written = sh.stage(DATE, {"analysis.json": "{}"}, root_dir=SANDBOX)
    check("合法檔名可寫入", written == ["analysis.json"] and (d / "analysis.json").is_file(), written)


def t20_public_text_map():
    print("\n[T20] PUBLIC_TEXT 對照完整（含 H10），且模組用到的每個碼都有固定文字")
    golden = {
        "H01": "應變資料不完整（H01）",
        "H02": "應變資料格式不符（H02）",
        "H03": "應變資料日期不一致（H03）",
        "H04": "應變資料時間異常（H04）",
        "H05": "應變資料不齊（H05）",
        "H06": "應變資料驗證失敗（H06）",
        "H07": "應變資料為空（H07）",
        "H08": "應變資料來源未經認可（H08）",
        "H09": "應變資料批次衝突（H09）",
        "H10": "應變資料封存紀錄不一致（H10）",
        "H90": "當日應變分析未注入（H90）",
        "H99": "應變資料驗證失敗（未分類）（H99）",
    }
    check("對照表與裁決文字逐字相同", sh.PUBLIC_TEXT == golden,
          [k for k in golden if sh.PUBLIC_TEXT.get(k) != golden[k]])
    check("H01–H09 語意未被 H10 影響", all(sh.PUBLIC_TEXT[k] == v for k, v in golden.items() if k <= "H09"), "")
    src = Path(sh.__file__).read_text(encoding="utf-8")
    used = sorted(set(__import__("re").findall(r'"H\d\d"', src)))
    used_codes = [u.strip('"') for u in used]
    missing = [c for c in used_codes if c not in sh.PUBLIC_TEXT]
    check("模組用到的碼全部有對照文字", missing == [], missing)
    check("每個碼的公開文字都是查表而來（含 H10）",
          sh.public_text(["H10"]) == golden["H10"], sh.public_text(["H10"]))


def main():
    print("沙箱：%s" % SANDBOX)
    print("模組：%s" % sh.__file__)
    before = repo_status()
    for fn in (t01_valid, t02_tampered_json, t03_missing_file, t04_no_manifest, t05_absent,
               t06_date_mismatch, t07_out_of_window, t08_extra_files, t09_schema, t10_empty_file,
               t11_lane, t12_duplicate_batch, t13_manifest_tampered, t14_disabled_with_data,
               t15_dry_run, t16_archive, t17_public_text, t18_dry_run_verdict, t19_stage_boundary,
               t20_public_text_map):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(fn.__name__ + " 例外", False, repr(e)[:200])
    os.environ.pop("LJ_EMERGENCY_HANDOFF", None)
    t00_repo_untouched(before)

    ok = sum(1 for _, b, _ in RESULTS if b)
    bad = [r for r in RESULTS if not r[1]]
    print("\n================ 合計 %d PASS / %d FAIL ================" % (ok, len(RESULTS) - ok))
    for n, _, d in bad:
        print("  ✗ " + n + "｜" + str(d))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())

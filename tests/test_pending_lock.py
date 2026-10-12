# -*- coding: utf-8 -*-
"""tests/test_pending_lock.py — TD-20261009-16 驗收測試（併發競態／故障注入／格式／逾時／守門）。

原則：全部在暫存目錄操作，**絕不觸碰正本** pending_decisions.json。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import pending_store  # noqa: E402

WORKER = BASE / "tests" / "_lock_worker.py"
PY = sys.executable
_ok = _fail = 0
FAILS = []


def ck(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  ✅ {name}")
    else:
        _fail += 1
        FAILS.append(name)
        print(f"  ❌ {name} {detail}")


def _mk(tmp: Path, n=1):
    p = tmp / "pending_decisions.json"
    p.write_text(json.dumps([{"title": f"base{i}"} for i in range(n)], ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _run_worker(p, title, extra=(), lock=None):
    extra = list(extra) + (["--lock", str(lock)] if lock else [])
    return subprocess.run([PY, str(WORKER), str(p), title, *extra],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def t1_concurrent(tmp):
    print("T1 併發競態（持鎖）：8 程序各自讀-改-寫，全部卡片必須存在")
    p = _mk(tmp, 1)
    _lk = p.with_name("shared.lock")
    procs = [subprocess.Popen([PY, str(WORKER), str(p), f"c{i}", "--sleep", "0.15", "--lock", str(_lk)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8", errors="replace") for i in range(8)]
    rcs = [pr.wait(timeout=120) for pr in procs]
    got = {c["title"] for c in json.loads(p.read_text(encoding="utf-8"))}
    want = {"base0"} | {f"c{i}" for i in range(8)}
    ck("T1 併發無遺失（9 張全在）", rcs == [0] * 8 and got == want, f"rc={rcs} 缺={want - got} 多={got - want}")


def t1b_negative(tmp):
    print("T1b 負向對照（不持鎖＝修復前行為）：慢寫者必須覆蓋快寫者的卡片 → 證明競態真實")
    p = _mk(tmp, 1)
    slow = subprocess.Popen([PY, str(WORKER), str(p), "slow", "--sleep", "1.2", "--nolock"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.4)
    _run_worker(p, "fast", ["--nolock"])
    slow.wait(timeout=60)
    titles = {c["title"] for c in json.loads(p.read_text(encoding="utf-8"))}
    ck("T1b 無鎖確實遺失（fast 被 slow 覆蓋掉）", "fast" not in titles and "slow" in titles, f"titles={sorted(titles)}")


def t2_fault_injection(tmp):
    print("T2 故障注入：os.replace 前拋例外 → 正本逐位元不變、tmp 清除")
    p = _mk(tmp, 2)
    before = p.read_bytes()
    real = os.replace
    try:
        os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("inject"))
        try:
            pending_store.atomic_write_json(p, [{"title": "should-not-land"}])
            ck("T2 故障時應拋例外", False, "未拋例外")
        except OSError:
            ck("T2 故障時拋例外", True)
    finally:
        os.replace = real
    ck("T2 正本逐位元不變", p.read_bytes() == before)
    ck("T2 tmp 已清除", not list(tmp.glob("*.tmp-*")), str(list(tmp.glob('*.tmp-*'))))


def t2b_fsync(tmp):
    print("T2b 中斷注入：寫 tmp 後、replace 前殺行程 → 正本不變、無殘檔")
    p = _mk(tmp, 2)
    before = p.read_bytes()
    code = (
        "import sys,os,json;sys.path.insert(0,r'%s');import pending_store;"
        "real=os.replace;os.replace=lambda *a,**k: os._exit(9);" % BASE
        + "pending_store.atomic_write_json(r'%s',[{'title':'x'}])" % p
    )
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True, timeout=60)
    ck("T2b 子程序被中斷（rc=9）", r.returncode == 9, f"rc={r.returncode}")
    ck("T2b 正本逐位元不變", p.read_bytes() == before)
    left = list(tmp.glob(f"{p.name}.tmp-*"))
    ck("T2b 崩潰殘檔確實存在（物理限制：被殺程序無法自我清理）", len(left) == 1, str([x.name for x in left]))
    pending_store.atomic_write_json(p, json.loads(p.read_text(encoding="utf-8")))
    ck("T2b 下一次寫入回收殘檔（已持鎖 → 殘檔必為崩潰殘留）", not list(tmp.glob(f"{p.name}.tmp-*")))


def t3_reject(tmp):
    print("T3 讀回驗證：內容非合法 JSON／非序列化物件 → 拒絕且正本不動")
    p = _mk(tmp, 1)
    before = p.read_bytes()
    try:
        pending_store.atomic_write_text(p, "{not json")
        ck("T3 非法 JSON 被拒", False, "未拒絕")
    except pending_store.WriteRejected:
        ck("T3 非法 JSON 被拒", True)
    try:
        pending_store.atomic_write_json(p, [object()])
        ck("T3 非序列化物件被拒", False, "未拒絕")
    except Exception:
        ck("T3 非序列化物件被拒", True)
    ck("T3 正本逐位元不變", p.read_bytes() == before)
    ck("T3 無 tmp 殘檔", not list(tmp.glob("*.tmp-*")))


def t4_format(tmp):
    print("T4 格式保持：CRLF 檔維持 CRLF、LF 檔維持 LF，且不混行")
    pc = tmp / "crlf.json"
    pc.write_bytes(json.dumps([{"a": 1}], ensure_ascii=False, indent=2).replace("\n", "\r\n").encode())
    pending_store.atomic_write_json(pc, [{"a": 1}, {"b": 2}])
    raw = pc.read_bytes()
    _lf, _crlf = raw.count(b"\n"), raw.count(b"\r\n")
    ck("T4 CRLF 保持", _lf == _crlf, f"LF={_lf} CRLF={_crlf}")
    pl = tmp / "lf.json"
    pl.write_bytes(json.dumps([{"a": 1}], indent=2).encode())
    pending_store.atomic_write_json(pl, [{"a": 1}, {"b": 2}])
    ck("T4 LF 保持", b"\r\n" not in pl.read_bytes())


def t5_timeout(tmp):
    print("T5 鎖逾時：他人持有 3s，timeout=0.5s → LockTimeout 且不寫入")
    p = _mk(tmp, 1)
    lock_path = tmp / "shared5.lock"
    holder = subprocess.Popen([PY, str(WORKER), str(p), "holder", "--hold", "3", "--lock", str(lock_path)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.0)
    before = p.read_bytes()
    try:
        with pending_store.locked(timeout=0.5, path=lock_path):
            ck("T5 取鎖應逾時", False, "竟取得鎖")
    except pending_store.LockTimeout:
        ck("T5 取鎖逾時（fail-closed）", True)
    ck("T5 逾時未寫入", p.read_bytes() == before)
    holder.wait(timeout=60)
    with pending_store.locked(timeout=5, path=lock_path):
        ck("T5 釋放後可取鎖", True)


def t6_diag(tmp):
    print("T6 鎖診斷與釋放：鎖檔含 pid、退出後可再取、同行程可重入")
    p = _mk(tmp, 1)
    lock_path = tmp / "pending_decisions.lock"
    with pending_store.locked(timeout=5, path=lock_path):
        with pending_store.locked(timeout=5, path=lock_path):
            ck("T6 同行程可重入", True)
    h = pending_store.lock_holder(lock_path)
    ck("T6 釋放後可讀到最後持有者資訊", h.get("pid") == os.getpid(), str(h))
    with pending_store.locked(timeout=5, path=lock_path):
        ck("T6 退出後可再取", True)


def t8_traceability(tmp):
    print("T8 卡數／卡別追溯：diff_keys 能點名被移除的卡片")
    before = ["id:A", "id:B", "id:C"]
    after = ["id:A", "id:C", "id:D"]
    d = pending_store.diff_keys(before, after)
    ck("T8 抓到移除的卡", d["removed"] == ["id:B"], str(d))
    ck("T8 抓到新增的卡", d["added"] == ["id:D"], str(d))


def t7_static_guard(tmp):
    print("T7 靜態守門：live 寫入者必須全數經 pending_store（防未來繞道）")
    import re
    offenders = []
    for f in BASE.glob("*.py"):
        if f.name.startswith(("_bak", "test_")) or f.name == "pending_store.py":
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "pending_decisions.json" not in src and "PEND" not in src:
            continue
        uses_store = "pending_store" in src
        writes = re.search(r"pending_decisions\.json\"\s*\)?\s*\.write_text|PEND\s*\)\s*\.write_text|PEND\.write_text", src)
        if writes and not uses_store:
            offenders.append(f.name)
    ck("T7 無繞道寫入者", not offenders, f"繞道={offenders}")


def main() -> int:
    print("=== TD-20261009-16 驗收測試（併發／故障／格式／逾時／守門）===")
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        t1_concurrent(tmp); t1b_negative(tmp)
        t2_fault_injection(tmp); t2b_fsync(tmp); t3_reject(tmp)
        t4_format(tmp); t5_timeout(tmp); t6_diag(tmp)
        t8_traceability(tmp); t7_static_guard(tmp)
    print(f"\n== 結果：{_ok} PASS / {_fail} FAIL ==")
    if FAILS:
        print("FAIL 清單:", FAILS)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

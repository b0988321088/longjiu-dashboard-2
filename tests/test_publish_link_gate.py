# -*- coding: utf-8 -*-
"""發布前連結閘門 + 四情境攔截測試（2026-10-12 工單 P3）

背景（2026-10-12 實踩）：線上儀表板按鈕「退休規劃」指向 retirement_plan_2026-10-12.html，
該檔只在本機產出、沒人入庫 → Pages 404 一整天。
根因之一：`check_dashboard_sync.py` 第 12 項（連結目標未進版控）在產線兩處呼叫都帶
`LJ_PREPUSH=1` → 永遠只印 ℹ️，push 前沒有任何一道會真的擋。
P1 修法：`regenerate_report.py` 在「已 stage、未 commit」時以**非** PREPUSH 模式跑同一支檢查。

本測試全程在 tempfile 沙盒執行（臨時 git repo／本地 bare remote／本地 HTTP server），
不碰正式 repo、不對外推送。覆蓋四個結案情境：
  A 未追蹤目標   → 發布前連結閘門攔截（S1／S2／S3）
  B 目標未發布   → --post-push 對線上 404 攔截（S4／S5）
  C 推送失敗     → 閘門拒絕、遠端不前進（S6／S7）
  D 舊 commit 阻塞→ 範圍內單一違規 commit 即擋整段（S6 的 range 版本）
另含兩條對照（負向）：已 stage → 放行；純報表＋[cioreviewed] → 放行（證明不是恆擋）。

執行：python -X utf8 tests/test_publish_link_gate.py
"""
from __future__ import annotations

import http.server
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" ｜{detail}" if detail and not cond else ""))


def _git(repo: Path, *args: str) -> tuple[str, str, int]:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def _run(cmd: list[str], cwd: Path, env_extra: dict | None = None, timeout: int = 180):
    import os
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


# --------------------------------------------------------------- A：未追蹤目標

GHOST = "ghost_report_2026-10-12.html"
MIN_INDEX = (f'<!DOCTYPE html><html><body><div class="card">測試</div>'
             f'<a href="{GHOST}">幽靈報表</a></body></html>\n')


def make_sync_fixture(prefix: str) -> Path:
    """複製真 check_dashboard_sync.py（含它需要的輸入）到沙盒，並建一個 git repo。"""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    for f in ("check_dashboard_sync.py", "links_config.py", "snapshot.json", "index_template.html"):
        src = REPO / f
        if src.exists():
            shutil.copy2(src, d / f)
    (d / "index.html").write_text(MIN_INDEX, encoding="utf-8")
    (d / GHOST).write_text("<html>ghost</html>\n", encoding="utf-8")   # 本機存在、尚未入庫
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@example.com")
    _git(d, "config", "user.name", "tester")
    _git(d, "add", "--", "check_dashboard_sync.py", "index.html", "links_config.py",
         "snapshot.json", "index_template.html")
    _git(d, "commit", "-q", "-m", "fixture")
    return d


def scenario_untracked() -> None:
    print("\n[A] 未追蹤連結目標 → 發布前連結閘門")
    d = make_sync_fixture("lkgate_a_")
    try:
        # S1：非 PREPUSH（P1 新模式）→ 必須 FAIL 且指名檔案
        r1 = _run([sys.executable, "check_dashboard_sync.py"], d)
        out1 = (r1.stdout or "") + (r1.stderr or "")
        check("S1 非 PREPUSH：未追蹤連結目標被擋（rc≠0）", r1.returncode != 0,
              f"rc={r1.returncode}")
        check("S1 訊息指名違規檔（Pages 會 404）",
              "連結目標未進版控" in out1 and GHOST in out1)

        # S2：原產線模式（LJ_PREPUSH=1）→ 只列 ℹ️（重現缺口，防止有人把它當成已具備攔截力）
        r2 = _run([sys.executable, "check_dashboard_sync.py"], d, {"LJ_PREPUSH": "1"})
        out2 = (r2.stdout or "") + (r2.stderr or "")
        check("S2 LJ_PREPUSH=1：同一情境只印 ℹ️、不擋（＝缺口成因）",
              ("待本次 commit 進版控" in out2) and ("連結目標未進版控" not in out2))

        # S3：負向對照 —— 檔已 stage → 該訊息必須消失（閘門不是恆擋）
        _git(d, "add", "--", GHOST)
        r3 = _run([sys.executable, "check_dashboard_sync.py"], d)
        out3 = (r3.stdout or "") + (r3.stderr or "")
        check("S3 對照：目標已 stage → 不再報『未進版控』", "連結目標未進版控" not in out3)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------- B：目標未發布

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # 靜音
        pass


def serve(directory: Path):
    handler = lambda *a, **k: _Quiet(*a, directory=str(directory), **k)  # noqa: E731
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def scenario_not_deployed() -> None:
    print("\n[B] 目標未發布（線上 404）→ --post-push 驗線上 200")
    d = make_sync_fixture("lkgate_b_")
    try:
        # 把 Pages base url 改指向本地 HTTP server（沙盒化，不對外連線）
        s = (d / "check_dashboard_sync.py").read_text(encoding="utf-8")
        s = s.replace('_BASE_URL = "https://b0988321088.github.io/longjiu-dashboard-2"',
                      '_BASE_URL = f"http://127.0.0.1:{__import__(\'os\').environ[\'LK_TEST_PORT\']}"')
        (d / "check_dashboard_sync.py").write_text(s, encoding="utf-8")

        # S4：線上缺 ghost 檔 → 必須 FAIL 且訊息為「非 200」
        srv_missing = Path(tempfile.mkdtemp(prefix="lkgate_srv_miss_"))
        (srv_missing / "index.html").write_text(MIN_INDEX, encoding="utf-8")   # 只服務 index.html
        httpd, port = serve(srv_missing)
        try:
            r4 = _run([sys.executable, "check_dashboard_sync.py", "--post-push"], d,
                      {"LK_TEST_PORT": str(port), "LJ_POSTPUSH_BUDGET": "5"})
            out4 = (r4.stdout or "") + (r4.stderr or "")
            check("S4 線上 404 被擋（rc≠0）", r4.returncode != 0, f"rc={r4.returncode}")
            check("S4 訊息為『線上連結非 200（Pages 404/未上線）』",
                  "線上連結非 200" in out4 and GHOST in out4)
        finally:
            httpd.shutdown(); httpd.server_close(); shutil.rmtree(srv_missing, ignore_errors=True)

        # S5：負向對照 —— 線上也有 ghost → 該訊息消失
        srv_full = Path(tempfile.mkdtemp(prefix="lkgate_srv_full_"))
        (srv_full / "index.html").write_text(MIN_INDEX, encoding="utf-8")
        (srv_full / GHOST).write_text("<html>ghost</html>\n", encoding="utf-8")
        httpd2, port2 = serve(srv_full)
        try:
            r5 = _run([sys.executable, "check_dashboard_sync.py", "--post-push"], d,
                      {"LK_TEST_PORT": str(port2), "LJ_POSTPUSH_BUDGET": "5"})
            out5 = (r5.stdout or "") + (r5.stderr or "")
            check("S5 對照：線上 200 → 不再報『非 200』", "線上連結非 200" not in out5)
        finally:
            httpd2.shutdown(); httpd2.server_close(); shutil.rmtree(srv_full, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------- C／D：推送失敗與舊 commit 阻塞

def make_push_sandbox() -> tuple[Path, Path]:
    """沙盒 repo + 本地 bare remote + 真 pre-push hook（不對外連線）。

    注意順序：base commit **只**含 README.md，hook 必須在 base commit 之後才建立 ——
    `.githooks/*` 本身是程式檔（CODE_RE），若被 `git add -A` 收進 base commit，
    base 這顆就會因「標籤通道不得推程式」被擋，測試前提直接失效（首輪實測踩到）。
    """
    repo = Path(tempfile.mkdtemp(prefix="lkgate_push_"))
    remote = Path(tempfile.mkdtemp(prefix="lkgate_remote_"))
    for a in (["init", "-q"], ["config", "user.email", "t@example.com"],
              ["config", "user.name", "tester"], ["config", "core.autocrlf", "false"],
              ["config", "core.hooksPath", ".githooks"]):
        _git(repo, *a)
    _git(remote, "init", "--bare", "-q")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "--", "README.md")
    _git(repo, "commit", "-q", "-m", "base [cioreviewed]")
    hooks = repo / ".githooks"
    hooks.mkdir()
    shutil.copy2(REPO / ".githooks" / "pre-push", hooks / "pre-push")
    (hooks / "pre-push").chmod(0o755)
    return repo, remote


def _remote_head(remote: Path) -> str:
    out, _, rc = _git(remote, "rev-parse", "clean-main")
    return out if rc == 0 else ""


def scenario_push_block() -> None:
    print("\n[C/D] 推送失敗與舊 commit 阻塞 → 閘門拒絕、遠端不前進")
    repo, remote = make_push_sandbox()
    try:
        # 前置 + S8（對照組先跑）：clean-main 建立 ＋ 純報表＋[cioreviewed] → 放行、遠端前進
        _, _, rc0 = _git(repo, "push", "origin", "HEAD:clean-main")
        base_remote = _remote_head(remote)
        check("S8-前置：純資料＋標籤通道可推（建立了 clean-main）", rc0 == 0 and bool(base_remote),
              f"rc={rc0}")

        (repo / "ok.html").write_text("<html>ok</html>\n", encoding="utf-8")
        _git(repo, "add", "--", "ok.html")
        _git(repo, "commit", "-q", "-m", "data: 報表產出 [cioreviewed]")
        _, _, rc8 = _git(repo, "push", "origin", "HEAD:clean-main")
        head_ok, _, _ = _git(repo, "rev-parse", "HEAD")
        check("S8 對照：純報表＋[cioreviewed] → 放行", rc8 == 0, f"rc={rc8}")
        check("S8 遠端 sha 與本機一致（推送確實生效）", _remote_head(remote) == head_ok)

        # S6：程式檔 commit 用 [cioreviewed] → TAG 通道不得推程式 → 擋
        good_remote = _remote_head(remote)
        (repo / "bad.py").write_text("print('x')\n", encoding="utf-8")
        _git(repo, "add", "--", "bad.py")
        _git(repo, "commit", "-q", "-m", "data: 偷渡程式 [cioreviewed]")
        bad_sha, _, _ = _git(repo, "rev-parse", "HEAD")
        o6, _, rc6 = _git(repo, "push", "origin", "HEAD:clean-main")
        check("S6 程式檔走標籤通道被擋（推送失敗）", rc6 != 0, f"rc={rc6}")
        check("S6 遠端未前進（未被污染）", _remote_head(remote) == good_remote)
        check("S6 訊息明示違規檔", "bad.py" in o6)

        # S7：v5 契約 —— destination 非 clean-main → 擋
        _, _, rc7 = _git(repo, "push", "origin", "HEAD:main")
        check("S7 destination 非 clean-main 被擋（不得繞過 v5 契約）", rc7 != 0, f"rc={rc7}")
        check("S7 遠端仍未被污染", _remote_head(remote) == good_remote)

        # S9（D：舊 commit 阻塞）：卡住的違規 commit 留在範圍內 → 後面再乾淨的 commit 也推不動
        (repo / "ok2.html").write_text("<html>ok2</html>\n", encoding="utf-8")
        _git(repo, "add", "--", "ok2.html")
        _git(repo, "commit", "-q", "-m", "data: 又一顆純報表 [cioreviewed]")
        o9, _, rc9 = _git(repo, "push", "origin", "HEAD:clean-main")
        check("S9 範圍內殘留違規 commit → 後續乾淨 commit 一併被擋（阻塞可驗）", rc9 != 0,
              f"rc={rc9}")
        check("S9 擋下訊息指名的是舊的違規 commit（不是新的那顆）",
              bad_sha[:12] in o9 and "bad.py" in o9, f"bad_sha={bad_sha[:12]}")
        check("S9 遠端仍未被污染", _remote_head(remote) == good_remote)
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(remote, ignore_errors=True)


def scenario_wiring() -> None:
    """[E] 接線守門：真原始碼的結構斷言（不是重寫一份邏輯來測）。

    端到端實跑整條 regenerate_report.py 需要真 commit/push，屬發布後才做的驗收；
    這裡以 AST 驗「P1 的擋必須真的守著 commit」——若有人把 `and _links_ok` 拿掉，
    或把檢查改回帶 LJ_PREPUSH，這條會立刻紅。
    """
    print("\n[E] 接線守門（AST：P1 的擋確實守著 commit、且不帶 LJ_PREPUSH）")
    import ast
    src = (REPO / "regenerate_report.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    def _call_seg(node) -> str:
        return ast.get_source_segment(src, node) or ""

    commit_lines, gate_lines, gate_segs = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            seg = _call_seg(node)
            # 精確定位「真的 git commit 呼叫」——不可用 'commit' 字樣，因為 helper 內也有
            # cio_approve 的 "--commit" 與 f-string {commit}，會把行號帶偏（2026-10-12 實踩）。
            if "'git', 'commit', '-m'" in seg:
                commit_lines.append(node.lineno)
            if "check_dashboard_sync.py" in seg:
                gate_lines.append(node.lineno)
                gate_segs.append(seg)
    commit_line = min(commit_lines) if commit_lines else 10 ** 9
    # 閘門＝「在 commit 之前、最靠近 commit 的那個 check_dashboard_sync 呼叫」
    gate_before = [n for n in gate_lines if n < commit_line]
    gate_line = max(gate_before) if gate_before else 10 ** 9
    gate_seg = ""
    if gate_before:
        gate_seg = [s for s, n in zip(gate_segs, gate_lines) if n == gate_line][0]

    # commit 是否被 `... and _links_ok` 守著
    guards_commit = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp):
            if {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)} & {"_links_ok"}:
                if node.lineno <= commit_line <= (node.end_lineno or node.lineno):
                    guards_commit = True

    check("S10 commit 由 `_links_ok` 守著（結構斷言）", guards_commit)
    check("S10 發布前閘門存在，且呼叫「本體」不帶 LJ_PREPUSH",
          bool(gate_seg) and "LJ_PREPUSH" not in gate_seg,
          f"gate_seg={gate_seg[:120]!r}")
    check("S10 閘門在 commit 之前執行（行號順序）", gate_line < commit_line,
          f"gate@{gate_line} commit@{commit_line}")
    check("S10 擋下時會取消 stage（不留 staged 殘留）",
          any("restore" in _call_seg(n) and "staged" in _call_seg(n)
              for n in ast.walk(tree) if isinstance(n, ast.Call)))


def main() -> int:
    print("=" * 60)
    print("發布前連結閘門／四情境攔截測試（沙盒，不連外、不推正式 remote）")
    print("=" * 60)
    scenario_untracked()
    scenario_not_deployed()
    scenario_push_block()
    scenario_wiring()
    print("\n" + "=" * 60)
    print(f"通過 {len(PASS)} 項，失敗 {len(FAIL)} 項")
    if FAIL:
        for f in FAIL:
            print(f"  ❌ {f}")
        return 1
    print("✅ 全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())

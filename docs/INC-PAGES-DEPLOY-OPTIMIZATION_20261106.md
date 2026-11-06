# INC-PAGES-DEPLOY-OPTIMIZATION：Pages 部署瘦身與發布穩定化（施工計畫書）

- 日期：2026-11-06　狀態：**草案（待獨立審查授權，不得施工）**
- 觸發：2026-11-06 三次 Pages deploy 逾時（build 16–17 秒成功、deploy 10 分 9 秒～10 分 23 秒失敗）
- 目的：讓日常日報／儀表板更新不再依賴空 commit 重觸發，也不再撞 10 分鐘上限
- 鐵則：**不得刪除唯一備份**；影片、歷史報告、備份一律「搬到封存位置」，不是刪掉

## 一、問題陳述（可驗證事實）

| 項目 | 現況 |
|---|---|
| 追蹤檔案 | 2,675 檔 |
| clean-main 內容總量 | **133.8 MB** |
| .git | 255 MB |
| Pages 建置方式 | 分支直出（有 `.nojekyll`、**無** `_config.yml`）→ 整包原樣上傳，無排除機制 |
| deploy 上限 | 10 分鐘（GitHub 固定）；今日失敗 3 次 |
| 影響 | 線上落後分支；20:35 以後的修正到 22:30 仍未上線 |

結論：這是**發布架構容量問題**，不是個別 commit 問題。

## 二、盤點（唯讀，git ls-tree 實測）

| 類別 | 檔數 | 大小 | 網站引用 |
|---|---|---|---|
| HTML（報表/日報） | 854 | 43.87 MB | 僅當期與被連結者 |
| 影片 mp4 | 6 | **41.13 MB** | **0 處引用** |
| 圖片 png/jpg | 201 | 29.35 MB | 引用 40 檔 5.04 MB／**未引用 161 檔 24.31 MB** |
| JSON | 546 | 4.49 MB | 部分由頁面 fetch（需保留當期） |
| 程式 .py | 485 | 5.04 MB | 非網站資產（但為本機產線，須留） |
| 文件 .md | 442 | 2.37 MB | 非網站資產 |
| 備份 snapshot/bak | 30 | 3.20 MB | 非網站資產 |
| 簡報/文件 pptx/docx | 31 | 1.35 MB | 非網站資產 |
| 音檔 mp3 | 5 | 1.13 MB | 非網站資產 |

- HTML 拆分：**11/01–11/06 僅 60 檔 1.69 MB**；其餘 794 檔 42.18 MB（多為 10 月及更早的歷史日報／報表）
- `index.html` 只連到 1 份當日日報，歷史日報不在導覽中

## 三、遷移清單（A 案：搬出 clean-main，保留於封存分支）

| # | 類別 | 範圍 | 大小 | 封存位置 |
|---|---|---|---|---|
| 1 | 影片 | `拼合_*.mp4` 全部 6 檔 | 41.13 MB | `archive-media` 分支 `media/` |
| 2 | 未引用圖片 | 161 檔（如 `_conv_img_*`、`_fullpage.png`、`_crop_*`、`pdf_extract/*`） | 24.31 MB | `archive-media` `images/` |
| 3 | 舊 HTML | 2026-10-24 以前的日報／報表（保留 10/24 起本波與 11 月全部） | ≈40 MB | `archive-media` `reports/<YYYY-MM>/` |
| 4 | 備份 | `snapshot.backup*`、`*.bak*` | 3.20 MB | `archive-media` `backup/` |
| 5 | 簡報/文件 | 31 檔 pptx/docx | 1.35 MB | `archive-media` `docs/` |
| 6 | 音檔 | `_tts_*.mp3` 5 檔 | 1.13 MB | `archive-media` `audio/` |

預期結果：clean-main **133.8 MB → 約 23 MB**。

**保留（不搬）**：`index.html`、當期與 10/24 起日報／資產差異／穿透／再平衡／成本／MTD／stress／emergency 頁、被引用圖片 40 檔、當期 JSON（含頁面 fetch 的 `macro_regime_*`、`mtd_data.json`、`dashboard_decisions.json` 等）、全部 `.py`（本機產線）、`.md` 文件、`dragon_assets.db`。

## 四、部署來源隔離（真正的治本）

改為 **GitHub Actions 產出 `_site` 後部署**，且 `_site` 由**同一支組裝腳本**產生（本機與 CI 共用，保證一致）：

```yaml
# .github/workflows/pages.yml
name: pages-allowlist-deploy
on:
  push: { branches: [clean-main] }
  workflow_dispatch:
permissions: { contents: read, pages: write, id-token: write }
concurrency: { group: pages, cancel-in-progress: true }
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Assemble site (fail-loud)
        run: python scripts/build_pages_site.py --out _site
      - uses: actions/upload-pages-artifact@v3
        with: { path: _site }
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: github-pages
    steps:
      - uses: actions/deploy-pages@v4
```

**組裝腳本 `scripts/build_pages_site.py`（規格）**
- 輸入：`scripts/pages_allowlist.txt`（每行一個 repo 相對路徑，含子目錄）
- 規則：①`index.html` 必存在（缺即 exit 1）②當期報表以檔名 regex 納入（預設 `2026-(10-(2[4-9]|3[01])|11-)`，可參數化）③allowlist 逐行複製，**保留原目錄結構**（`_site/<原路徑>`）；缺檔 → **exit 1 並列出缺檔**（不靜默跳過）
- 護欄：輸出總量 > 25 MB 或 `index.html` 缺失 → exit 2，阻擋部署
- 收尾：寫 `_site/.nojekyll`、`_site/404.html`（導向「本頁已封存，請回首頁或封存說明」）
- 同一支腳本在本機執行 `python scripts/build_pages_site.py --out _tmp_site` 即得與 CI 相同結果（驗收步驟 4 用）

**allowlist 產生器 `scripts/gen_pages_allowlist.py`（規格）**
- 掃描所有 html/js：`src|href` 屬性、`fetch('…')`／`fetch("…")`、`url(…)`，抽出站內相對資產（忽略 `http(s)://`、`mailto:`、`#`）
- 解析到 repo 相對路徑（去除 query/hash）；同名不同目錄 → 全部納入
- 輸出排序後的 allowlist ＋ `--report` 印出「被引用但不存在」清單（此清單必須為空才可施工）

**預期效果**：artifact 由 133.8 MB 降到 **≈10–12 MB**；deploy 由 10 分鐘降到 1–2 分鐘。
**回滾**：Pages 設定切回 `Deploy from a branch: clean-main` 即復原（workflow 保留停用），屬獨立可回滾步驟。

## 五、驗收（全部通過才算完成；每項標明執行者）

| # | 項目 | 執行者 | 判定 |
|---|---|---|---|
| 1 | 內部連結完整：掃 `_site` 全部 HTML 的站內 `href/src/fetch`，目標檔必須存在於 `_site`；**外部 http(s) 連結只記錄不判定** | CI（自動）＋本機 | 0 個站內斷鏈；外部連結清單另附 |
| 2 | 線上等值：`_site` **全量逐檔 md5** 對線上同名檔（cache-buster 參數繞 600s 快取） | 本機 | 差異 0 |
| 3 | 數字一致：`check_penetration_consistency.py`、`check_narrative_numbers.py` | 本機 | 全綠 |
| 4 | 本機 `_site` 與 CI `_site` 一致：CI 上傳 artifact 內 `manifest.json`（路徑+md5）與本機比對 | CI 產出＋本機比對 | 差異 0 |
| 5 | 部署指標：deploy 耗時、artifact 大小記錄於 commit message | CI（自動） | <2 分鐘、<20 MB |
| 6 | 倉庫狀態：`git rev-list --count origin/clean-main..HEAD == 0`、`git status` 僅剩預期未追蹤目錄 | 本機 | 0／符合 |
| 7 | 封存完整性：`archive-media` 上移除清單逐檔存在且 md5 與移除前一致（**先算 md5 再搬**） | 本機 | 差異 0 |
| 8 | 不依賴空 commit：以正常日報產出觸發一次部署並上線 | CI＋本機 | 成功上線 |

## 六、風險與對策

| 風險 | 對策 |
|---|---|
| 舊連結 404 | 三層：①保留 10/24 起全部報表 ②提供 `404.html` 導向首頁與封存說明（不再回空白頁）③封存分支保留原檔可查 |
| 頁面 fetch 的 JSON 被漏 | allowlist 由 `gen_pages_allowlist.py` 掃描 `fetch(` 產生，且「被引用但不存在」必須為空才可施工 |
| 影片為唯一備份 | 先建封存分支、算 md5、推送成功後，才從 clean-main 移除；本機檔案不動 |
| `git rm` 誤刪未封存檔 | 施工前產出「移除清單 CSV ＋ md5」，移除只依該清單逐檔執行；執行後立刻跑封存完整性驗收（§五-7） |
| Actions 部署需切換 Pages 來源 | 切換為獨立步驟，記錄切換前設定；失敗即切回 `Deploy from a branch`（回滾 < 5 分鐘） |
| 產線持續產生歷史檔 | 本批先一次性；後續立卡「日報只保留近 30 天於 clean-main、其餘自動搬封存」 |
| 對外公開面（repo public） | 本批不處理敏感資料 P0；僅記錄 Pages 站已不含大型非網站檔 |

## 七、施工順序（一次完成，不拆批；每步含驗證）

| 步 | 動作 | 驗證 |
|---|---|---|
| 1 | `scripts/gen_pages_allowlist.py --report` 產生 allowlist 與「被引用但不存在」清單 | 清單必須為空；allowlist 筆數與 §二引用數相符 |
| 2 | 產出移除清單 CSV（類別、路徑、bytes、md5） | CSV 筆數／總量與 §三一致（≈111 MB） |
| 3 | 建 `archive-media` orphan 分支，依 CSV 逐檔搬入並推送 | 分支上逐檔存在且 md5 相同（全量比對） |
| 4 | clean-main 依 CSV 以 `git rm` 移除（工作區同步刪除；本機已於步 3 有副本） | `git status` 僅顯示清單內檔案；無其他變更 |
| 5 | `.gitignore` 加入規則（`拼合_*.mp4`、`_conv_img_*`、`_fullpage*.png`、`snapshot.backup*`、`*.bak*`、`_tts_*.mp3`、`docs/*.pptx`） | 新產生檔案不再入版控（以一次 dry-run 驗證） |
| 6 | 新增 `scripts/build_pages_site.py`、`scripts/gen_pages_allowlist.py`、`.github/workflows/pages.yml` | 本機跑 `--out _tmp_site` 成功、大小與 §四預期相符 |
| 7 | 本機跑驗收 §五-1、§五-2（以 `_tmp_site` 對照本機檔案）、§五-4（以本機 manifest 對照 CI artefact） | 全綠 |
| 8 | 送 CIO 審查（含兩個腳本、workflow、移除清單 CSV、封存證據） | APPROVE、blocking=[] |
| 9 | 授權後 commit／push（分兩顆：`archive` 遷移資料、`workflow+scripts` 程式） | 推送閘門通過、待推 0 |
| 10 | 切換 Pages 來源為 GitHub Actions（獨立步驟） | 切換前截圖設定；失敗即回滾 |
| 11 | 部署後跑 §五-2、§五-5、§五-6、§五-8 | 全綠；空 commit 不再是常態手段 |

## 八、明確不做

- 不刪任何唯一備份、不刪影片、不刪歷史報告（只搬）
- 不動 `snapshot.json`／`dragon_assets.db` 真值內容
- 不改任何產線腳本邏輯（除 allowlist 產生器與 workflow 新增）
- 不以空 commit 重觸發作為常態手段
- 不在本批處理公開面敏感資料（既有 P0 另案）

## 附錄 A：本次盤點量化依據

- 檔案清單與大小：`git ls-tree -r -l HEAD`
- 引用掃描：855 個 html/js 內 `src|href` 指向的 41 個資產名
- 大型未引用媒體前 6：`拼合_3片_v1.mp4` 9.93 MB、`拼合_13_v4.mp4` 6.96 MB、`拼合_13_v3.mp4` 6.96 MB、`拼合_13_v2.mp4` 6.61 MB、`拼合_13_final.mp4` 6.54 MB、`拼合_v1.mp4` 6.12 MB

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""usd_advisory.py — 美元曝險 advisory_only 的唯一語意入口（2026-10-07 使用者裁決）。

背景：美元曝險自動化只是把真值收回來，不是重新制定資產政策。60/65/70 三級門檻與
2026-09-12「放寬到 60」的政策存在衝突 → 衝突留給 10 月戰略檢討，程式不得把它轉成
資產操作。含 LLM 在內的所有下游都必須吃同一個旗標，不得各自表述。

提供四件事（單一來源，其他模組一律呼叫這裡）：
  is_advisory(snap)   → bool：該項目前是否為「只顯示、不觸發」
  label(snap)         → str ：顯示用的門檻字樣（'🟡 僅顯示 門檻' 或 '紅線'）
  prompt_block(snap)  → str ：餵進 LLM prompt 的硬性約束段（非 advisory 回空字串）
  violations/scrub    → 產出端防呆（白名單：提及即違規）

prompt_block 為空字串時，呼叫端的 f-string 只會多一個空行，不影響既有 prompt 語意。
"""
from __future__ import annotations

import re
import unicodedata


def _mon(snap) -> dict:
    return (snap or {}).get("usd_exposure_monitor") or {}


def is_advisory(snap) -> bool:
    """美元曝險是否為 advisory_only（只顯示、不觸發資產調整）。缺旗標視為 False（維持舊行為）。"""
    return bool(_mon(snap).get("advisory_only"))


def label(snap) -> str:
    """顯示用門檻字樣：advisory → '🟡 僅顯示 門檻'；否則沿用 '紅線'。"""
    return "🟡 僅顯示 門檻 " if is_advisory(snap) else "紅線"


# ── 裁決②③（2026-10-07）：政策門檻唯一來源 ＋ 觀測線命名 ──────────────────────
# 2026-10-07 使用者裁決②：usd_exposure_monitor 不再另存一份政策門檻（避免「兩處
# 改一處」的漂移），唯一來源 = snapshot.thresholds.美元曝險_pct。
# 2026-10-07 使用者裁決③：命名改為 60＝目標值、65＝黃色觀察、70＝高曝險觀察線、
# >70 ＝ 僅顯示（70 已非 action trigger，故不再叫「紅線」）。
# 本節是「政策門檻」的唯一讀取入口，其他模組一律呼叫這裡，不得各自讀 snapshot。
def policy(snap) -> dict:
    """回 {'目標','黃','紅','來源'}（％）。唯一來源＝thresholds_2026_0915.美元曝險_pct。"""
    _all = (snap or {})
    t = ((_all.get("thresholds_2026_0915") or _all.get("thresholds") or {})
         .get("美元曝險_pct") or {})
    out = {}
    for k in ("目標", "黃", "紅"):
        v = t.get(k)
        out[k] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    if out["目標"] is None:
        # 回溯相容：舊 snapshot 只在 usd_exposure_monitor.threshold 存門檻（2026-10-07 已移除）
        v = _mon(snap).get("threshold")
        out["目標"] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    out["來源"] = "snapshot.thresholds_2026_0915.美元曝險_pct"
    return out


def cap(snap):
    """目標值（％）；缺真值回 None（呼叫端自行決定是否以顯示用 fallback 頂替）。"""
    return policy(snap).get("目標")


def tier_limit_text(snap) -> str:
    """顯示用門檻字樣：目標值 60%／黃色觀察 65%／高曝險觀察線 70%。"""
    p = policy(snap)

    def _f(k):
        v = p.get(k)
        return "{:.0f}".format(v) if isinstance(v, (int, float)) else "—"

    return ("目標值 {}%／黃色觀察 {}%／高曝險觀察線 {}%"
            .format(_f("目標"), _f("黃"), _f("紅")))


def tier(snap, val) -> str:
    """觀測等級字樣（不含動作語意）：高曝險觀察線／黃色觀察／目標值內／無真值。"""
    p = policy(snap)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return "無真值"
    r, y = p.get("紅"), p.get("黃")
    if isinstance(r, (int, float)) and val >= r:
        return "高曝險觀察線"
    if isinstance(y, (int, float)) and val >= y:
        return "黃色觀察"
    return "目標值內"


def status_text(snap, val) -> str:
    """監控狀態字串（裁決③命名）：只描述事實，不含任何處置語意。"""
    p = policy(snap)
    _t = tier(snap, val)
    _tail = "（僅顯示：不觸發資產調整；政策門檻待 10 月戰略檢討）"
    _g, _y, _r = p.get("目標"), p.get("黃"), p.get("紅")
    if _t == "無真值":
        return "⚠️ 無真值" + _tail
    if _t == "高曝險觀察線":
        return "🟡 {}% ≥ 高曝險觀察線 {:.0f}%{}".format(val, _r, _tail)
    if _t == "黃色觀察":
        return "🟡 {}% 位於黃色觀察區 {:.0f}~{:.0f}%{}".format(val, _y, _r, _tail)
    if isinstance(_g, (int, float)) and val >= _g:
        return "🟢 {}% ≥ 目標值 {:.0f}%（未進觀察區）{}".format(val, _g, _tail)
    return "🟢 {}% < 目標值 {}%{}".format(val, "{:.0f}".format(_g) if isinstance(_g, (int, float)) else "—", _tail)


def prompt_block(snap) -> str:
    """LLM prompt 專用硬性約束段。非 advisory 時回空字串（不改變既有 prompt）。

    第三版（CIO 三輪 REJECT 後）：不再把數字、門檻、紅線餵給 LLM，改成整項禁談 ——
    把防線前移到輸入端（沒有素材，就沒有可被轉成動作的內容），再由產出端白名單兜底。
    """
    if not is_advisory(snap):
        return ""
    return (
        "【美元曝險硬性約束（2026-10-07 使用者裁決）】"
        "美元曝險本項目前為「🟡 僅顯示」、政策門檻待 10 月戰略檢討，不得作為任何行動依據："
        "①本段敘述不得出現『美元曝險／美元部位／美元比重／外幣曝險／外幣配置／美元計價』等字樣，"
        "也不得引用其數字或比率（該項只由 UI 以「🟡 僅顯示」呈現）；"
        "②嚴禁就此項提出任何評價、方向或處置（含減碼、降低、壓回、加碼、提高、調整、重新分配、"
        "換匯、轉台幣等任何寫法）；"
        "③其他風險（科技集中、US30Y、台股／美股／債券桶位等）若另有依據可獨立建議，但不得與美元曝險掛勾。\n"
    )


# ── 卡②（2026-10-07）：硬性防呆 — 白名單架構 v9 ──────────────────────────────
# 演進：v1/v2 動作詞清單（CIO 證明等義改寫無窮）→ v3 提及即違規（允許條件太鬆）
#      → v4 允許詞彙集（只檢漢字）→ v5 追加非漢字（列舉不全）→ v6 字元類別白名單
#      → v7 正規化／分隔符消除前移到偵測入口 → v8 方向詞黑名單＋名詞同義詞＋HTML 實體
#      → v8.1 去 HTML 標籤（美<b>元</b>）＋USD 主體統一
# v9（CIO 第八/九輪根因建議）：**廢除「幣別 × 名詞 × 鄰接窗口」的有限清單**。
#   第九輪實證 美元金額/市值/現金/存量、美圓、美國貨幣、綠鈔、以及
#   「美元在整體投資組合的曝險比重偏高，建議減碼」全數繞過 → 列舉必漏。
#   改為單一 fail-closed 規則：
#   R1 _BROAD_CUR_RE：句中出現「廣義幣別主體」（美元/美金/美圓/美鈔/美刀/美幣/外幣/外匯/
#      US(D)/綠鈔/美國貨幣/美系貨幣）→ 該句必須通過白名單，否則即違規。
#   R2 白名單 _allowed_mention：含「僅顯示/只顯示」標記 ＋ 無方向／處置詞 ＋ 字元全在允許集。
#   R3 豁免 _EXEMPT_RE＋_clean_ascii：基金／帳戶／保單等正規名稱（美元避險月配、外幣組合存款、
#      美元定存/計價/保單…）且無可行動詞、無小寫拉丁／其他語系字母時放行
#      （第三輪 CIO 要求：合法名稱不得被破壞；第九輪：`美元計價資產 reduce 30%` 必須擋）。
#   I1 _norm()：HTML 實體解碼 ＋ 零寬／格式字元移除 ＋ 去 HTML 標籤 ＋ NFKC
#   I2 _compact()：再移除空白標點 → 偵測吃 compact（分隔符／夾字規避失效）
#
# 已知限制（明列；CIO 一～九輪要求記錄）：
#   L-A 白名單對純事實句的誤殺（scrub 只作用於 LLM 段落與簡報，不影響帳務資料）
#   L1 保護面＝三段 LLM 輸出（含快取寫入前中和）＋ build_final（全頁兜底）＋
#      check_usd_advisory.py 掃描的當日 LLM 產出物
#   L2 範圍界線（使用者裁決）：不含美元曝險主體的桶位／現金政策建議不判
#   L3 判定單元＝句子（。！換行）；跨句與跨行切詞不判（避免連坐誤殺）
#   L4 未被 _norm／_compact 覆蓋的極端構造（如以圖片承載文字）不在文字層防線範圍內
#   L5 真值名稱遮蔽（C1）以 snapshot 推導；資料中沒有的名稱用語（例：純描述性的「美元定存」）
#      會被中和（fail-closed，安全方向）
#   L6 針對「具體某一檔」的行動敘述（例：M&G入息基金A(美元避險月配)F 應轉台幣）在名稱被遮蔽後
#      不再觸發 —— 本卡保護對象是「美元曝險」這個維度，不是每一檔美元計價標的的個別處置
# v13（第十三輪 CIO 兩點結構性修正）：
#   C1 遮蔽收斂為「名稱欄鍵」（_MASK_KEY_RE：name／fund／帳戶／account／標的／label／ticker／保單名）。
#      v12 以「含廣義幣別」為由遮蔽任何字串 → 維度級政策字串（usd_exposure_monitor/rule、
#      debt_cleansing_monitor/對應配置、investment_direction_correction/方向）成了通行盾。
#   C2 canonical 新增「禁箭頭／禁帶號數字」：`美元曝險僅顯示 100%→0%。`／`-100%` 曾以符號通關。
# v14（第十四輪 CIO）：C2 改為**字元白名單**（不再「類別白名單＋有限黑名單」）——
#   ASCII 僅允許英數與非運算符標點、非 ASCII 僅允許指定 emoji 與 Po/Ps/Pe/Zs/Nd；
#   並以 codepoint 區塊封鎖全部 Unicode 箭頭區（U+2190–21FF／2700–27BF／27F0–27FF／
#   2900–297F／2B00–2BFF／1F800–1F8FF）。`⇨`／`➔`／`≥`／`–`／`～`／`全數台幣` 皆已關閉。
# v15（第十五輪 CIO：白名單字元可拼出方向／目標詞，CIO 自述「完全關閉接近語意判別不可能」）：
#   canonical 再加**結構事實**條件 —— 顯示行的現值必定在標記之前（先有曝險數字才談只顯示）：
#   ①標記不得先於主體 ②主體與標記之間必須有百分比現值 ③標記之後不得出現超過一個百分比。
#   故 `美元曝險僅顯示目標 0%。`／`底線0%`／`未達標` 一律出局，且不靠逐字列舉方向詞。
# v16（第十六輪 CIO：canonical 現值槽可塞目標值 —— `美元曝險目標台幣100% 僅顯示（目前 70.5%）。`
#   ／`僅顯示 門檻 0%。`／`僅顯示 零。`；CIO 註明**非**「語意判別不可能」、可用資料綁定修補）：
#   ①canonical 行內百分比必須 ∈ snapshot 推導集合｛現值、門檻、目標拆分｝＝現值 70.5／門檻 60／
#     台幣 40（分項零值刻意不入集，避免「目標 0%」與真值 0.0% 混淆）；集合為空即 fail-closed。
#   ②canonical 禁中文數字（零／一半…無法用百分比集合表達的目標值）。
#   ③修 scrub 與 violations 判定不一致：`scrub` 原呼叫 `clause_violation(sent)` **漏傳 snap**，
#     導致「偵測得到、中和不掉」；現改傳 snap，且 `clause_violation` 缺 snap 一律 fail-closed。
# v17（第十七輪 CIO 兩阻擋項，皆標註「非語意判別不可能」）：
#   ①資料綁定只殺「集合外」值，集合內值仍可拼目標語意（`美元曝險 70.5% 僅顯示 目標 60%。`／
#     `僅顯示 底線 40%。`／`僅顯示 維持 60%。`，21/27 通過）→ canonical 追加：標記之後的百分比
#     **必須緊接「門檻」**（本管線唯一合法的標記後數字），並禁無數字的方向詞 `目標`／`維持`／
#     `(?<!現金)底線`（`現金底線` 為真值標籤，豁免）。
#   ②`scrub` 原條件 `and _NEUTRAL not in line` 使「行內已含中性敘述」的違規句逃過中和
#     （hits>0 卻 kept=True）→ 改為逐句處理：該行已有中性敘述時逕行移除違規句，否則插入一次。
# v18（第十八輪 CIO：標記後數字只綁標籤不綁值 —— `門檻 40%`／`門檻 70.5%`／`政策門檻 40%` 通行，
#   因 40（台幣分項）與 70.5（現值）同屬真值集合。CIO 註明可修、非語意判別不可能）：
#   canonical 標記後的百分比**必須等於 snapshot 的真門檻（60）**，非僅須 ∈ 真值集合；
#   取不到真門檻即 fail-closed（`_canon_threshold`）。
# v19（第十九輪 CIO 三阻擋項，同族「值槽」缺口；CIO 註明皆可修、非語意判別不可能）——
#   採 A 案一次收完：**逐槽綁值**
#   ①標記前的百分比必須等於真實現值（現 70.5）—— `門檻 40% 僅顯示`／`40% 僅顯示（門檻 60%）` 出局
#   ②標記後的**所有數字**（含不帶 % 的裸數字）一律須掛「門檻」且等於真門檻 60
#     —— `僅顯示 門檻 40。`／`政策門檻 40。` 出局
#   ③日期成分（`10 月`）與千分位金額（`889,623`）豁免，真值 KPI 列不受影響
#   `_canon_current()` 取真實現值；現值或門檻任一取不到即 fail-closed。
# v20（第二十輪 CIO 兩阻擋項，皆機械可修）：
#   ①逗號／日期豁免被濫用：原「含逗號即豁免」使 `門檻 0,0%`／`門檻 40,0%`（全形逗號亦然）
#     繞過逐槽綁值；`門檻 40 月。` 亦以日期豁免逃逸。→ 改為**先判門檻槽**（凡緊接門檻者
#     一律須等於真門檻，不受任何豁免），非門檻槽才適用豁免，且千分位須為正規分組
#     `\d{1,3}(,\d{3})+`（如 `889,623`）。
#   ②canonical 行內 ASCII 方向詞全數通行（`僅顯示 SELL。`／`cut USD exposure.`／`GO LONG USD.`
#     ／`switch to TWD.`）—— 卡片核心是「僅顯示」不得夾帶指令。→ canonical 行內 ASCII 字母串
#     只允許 `USD`（幣別主體）與 `advisory`（標記），其餘一律出局。
# v21（第二十一輪 CIO 三阻擋項，皆機械可修）：
#   ①非 ASCII 數字腳本（阿拉伯-印度 `٤٠`／天城文 `४०`）NFKC 不折疊 → 不在 `_NUM_RE`／`_PCT_RE`
#     掃描範圍，也不被字元白名單拒絕（Nd）→ 完全逃逸「標記後數字＝真門檻」。→ `_norm` 追加
#     「所有 Unicode Nd 折成 ASCII 數字」，使偵測與綁值看到同一組數字。
#   ②金額豁免未看尾隨字元：`0,000%。`／`40,000%。` 以「正規分組＋%」冒充金額豁免通關
#     （真值金額 `889,623` 不帶 %）→ 帶 `%` 者一律不豁免。
#   ③門檻槽內非正規千分位 `門檻 6,0%` 去逗號後＝60 而放行 → 門檻槽禁逗號（只允許純十進位）。
#   （L2 不變：原文即不含廣義幣別主體的政策句不在本卡範圍 —— 例：`🔴 下一階段必須降低…至 0%。`）
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad\u034f]")
_TAG_RE = re.compile(r"<[^<>]{0,60}>")
_ADVISORY_TOKEN_RE = re.compile(r"(?i)advisory(?:_only)?")
# 允許詞彙集（純事實／僅顯示敘述會用到的漢字）
_ALLOWED_VOCAB = set(
    "美元美金外幣外匯曝險曝险暴險暴险部位比重佔比占比資產资产風險风险水位"
    "持倉持仓餘額余额倉位仓位比例敞口份额份額比率头寸頭寸"
    "門檻政策戰略檢討月待口徑顯示僅只不觸發維持觀察監控追蹤"
    "為是的了在與和及約以上以下超過超未無目前現況若則但且而"
    "底層因子主真數量值級項合計共計"
    "說明註記參考資訊來源計算口徑"
    # 第十四輪 CIO：白名單字元可拼出處置語（`美元曝險僅顯示，全數台幣。` 因「安**全**」「數**量**」
    # 而入集）→ 移出 全／數，避免允許集本身成為語意容忍面。
    "現金底線可動用本金市值淨值報價日價格匯率台幣美股台股債券基金保單證券帳戶活存安達標缺"
    "零一二三四五六七八九十百千萬亿%．."
)
# 允許的 Unicode 類別：數字、標點、符號（含 emoji）、空白
_ALLOWED_CATS = ("Nd", "Nl", "No", "Po", "Ps", "Pe", "Pd", "Pc", "Sm", "Sc", "Sk", "So", "Zs")

# ── v12 判定契約（第十二輪 CIO 揭示 v11 自我矛盾後定版）───────────────────────
# 演進（1～11 輪全部走過一次）：動作詞清單 → fail-closed 詞庫 → 提及即違規 → 允許詞彙集
# → 字元類別白名單 → 正規化前移 → 主體家族 → 廣義幣別主體 → 豁免正白名單。
# 第十二輪 CIO 實測證明 v11 自我矛盾：豁免白名單把「snapshot 名稱欄的漢字」收進可通行字集，
# 而名稱欄含 轉／改／收 等動詞字 → `美元定存部位轉台幣。`／`美元計價資產轉台幣。` 反而通關；
# 且註明「自測集是有限列舉，147/147 全綠不代表無洞」。故 v12 不再以任何詞彙表判別語意，
# 改為兩條**結構契約**（可窮盡、不列舉語意）：
#   C1 真值名稱遮蔽：先以 snapshot 推導的名稱字串遮蔽（基金／帳戶／保單／商品名等）。
#      遮蔽後不再含幣別主體 → 不在本卡範圍（合法名稱不會被誤殺，第三輪 CIO 要求）。
#   C2 遮蔽後仍含廣義幣別主體之句 → 唯一通行證＝canonical 行（含「僅顯示／只顯示」標記，
#      且不含方向／處置詞、字元全在允許集）。沒有動詞表、沒有名稱詞彙、沒有豁免詞。
#   C3 判定單元＝句子；跨句不判（L3）。
_BROAD_CUR_RE = re.compile(
    r"(?i)(us\s?\$|us\s?dollar|dollar\s?index|greenback|buck|dxy|usd|鎂|镁|"
    r"美[元金圓圆鈔钞刀幣币]|美系[貨货][幣币]|美[國国][貨货][幣币]|美[匯汇]|美國[錢钱]|美[紙纸]|"
    r"外[幣币匯汇]|綠鈔|绿钞)")
# 拉丁正規化幣別（U.S. dollar → usdollar、US-Dollar → usdollar）；第十一輪 CIO B3。
_CUR_LATIN = ("usdollarindex", "dollarindex", "usdollars", "usdollar",
              "dollars", "dollar", "greenbacks", "greenback", "bucks", "buck", "usd", "dxy")
# 同形字正規化（第十二輪 CIO：`UЅD` 以西里爾 Ѕ 繞過 NFKC）→ 於 _norm 入口映射回 ASCII。
_HOMOGLYPH = {
    "А": "A", "В": "B", "С": "C", "Е": "E", "Ѕ": "S", "І": "I", "Ј": "J", "К": "K", "М": "M",
    "Н": "H", "О": "O", "Р": "P", "Т": "T", "У": "Y", "Х": "X", "З": "3", "а": "a", "в": "b",
    "с": "c", "е": "e", "ѕ": "s", "і": "i", "ј": "j", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "т": "t", "у": "y", "х": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H",
    "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "Ꮪ": "S", "ꓢ": "S", "ᅟ": "", " ": " ",
}

# 名稱欄位判定（C1 遮蔽只作用於這些鍵；第十三輪 CIO 阻擋 1：v12 對「任何含廣義幣別的字串」
# 都遮蔽，導致維度級政策字串（usd_exposure_monitor/rule、debt_cleansing_monitor/對應配置、
# investment_direction_correction/方向）成了「通行盾」——把指令接在其後即整句放行。
# 故收斂為真正的名稱欄：name／fund／帳戶／account／標的／label／ticker／保單名。
# 刻意不收 `policy`（會撞到 redline_policy 等政策鍵）與 `id$`。
_MASK_KEY_RE = re.compile(r"(name|fund|帳戶|account|標的|label|ticker|保單名)", re.I)
_NAME_KEY_RE = _MASK_KEY_RE        # 回溯相容別名
_DT_CACHE: dict = {}


def _data_terms(snap) -> tuple:
    """C1：從 snapshot 推導「真值名稱字串」集合（含幣別主體的短字串＋名稱欄字串）。

    只取 3～80 字的字串：太短易誤遮、太長（段落）會讓整段失去檢查意義。
    推導失敗一律回空集合（fail-closed：不遮蔽 → 走 canonical 契約）。
    """
    key = (id(snap), len(snap) if hasattr(snap, "__len__") else 0)
    v = _DT_CACHE.get(key)
    if v is None:
        terms = []

        def _walk(o, k=""):
            if isinstance(o, dict):
                for kk, vv in o.items():
                    _walk(vv, str(kk))
            elif isinstance(o, list):
                for vv in o:
                    _walk(vv, k)
            elif isinstance(o, str):
                # 第十三輪 CIO 阻擋 1：只遮蔽「名稱欄」字串 —— 不再以「含廣義幣別」為由遮蔽，
                # 否則維度級政策字串（rule／裁示／對應配置）會變成通行盾。
                if 3 <= len(o) <= 80 and _MASK_KEY_RE.search(k):
                    terms.append(o)

        try:
            _walk(snap)
        except Exception:
            pass
        uniq = set()
        for t in terms:
            # 純幣別字串（"USD"／"美元"／"美金"）不遮蔽：否則 `USD曝險…` 會被遮成 `◆曝險…`
            # 而失去偵測（第十二輪自測實證）。遮蔽只針對「帶名稱內容」的字串。
            residue = _BROAD_CUR_RE.sub("", t)
            residue = re.sub(r"[\s()（）【】\[\]、,，./:%\-]", "", residue)
            if len(residue) < 2:
                continue
            uniq.add(t)
            uniq.add(unicodedata.normalize("NFKC", t))
        v = tuple(sorted((t for t in uniq if len(t) >= 3), key=len, reverse=True))
        _DT_CACHE[key] = v
    return v


def _mask_data(s: str, snap) -> str:
    """C1：把真值名稱字串換成「◆」。遮蔽後不再含幣別主體者 → 視為合法名稱，放行。"""
    if not snap:
        return s
    out = s
    for t in _data_terms(snap):
        if t in out:
            out = out.replace(t, "◆")
    return out


def _norm(s: str) -> str:
    """同形字映射 ＋ HTML 實體解碼 ＋ 移除零寬／格式字元 ＋ 去 HTML 標籤 ＋ NFKC。

    第八輪 CIO：`&#32654;&#20803;曝險…` 前端會渲染回「美元曝險」卻繞過文字層 → 先 html.unescape。
    第十二輪 CIO：`UЅD` 以西里爾同形字繞過 NFKC → 先做 _HOMOGLYPH 映射。
    """
    import html
    t = str(s).translate(str.maketrans(_HOMOGLYPH))
    t = html.unescape(_ZERO_WIDTH_RE.sub("", t))
    t = _TAG_RE.sub("", t)                      # HTML 標籤夾字（美<b>元</b>曝險）
    t = unicodedata.normalize("NFKC", t)
    # 第二十一輪 CIO 阻擋 1：阿拉伯-印度 `٤٠`／天城文 `४०` 等非 ASCII 數字腳本，NFKC 不折疊
    # → 既不被 `_NUM_RE` 掃到、也不被字元白名單拒絕（Nd）→ 完全逃逸「標記後數字＝真門檻」。
    # 解法：把所有 Unicode 十進位字元（Nd）折成 ASCII 數字，使偵測與綁值看到同一組數字。
    if any(unicodedata.category(ch) == "Nd" and not ch.isascii() for ch in t):
        t = "".join(str(unicodedata.digit(ch)) if (unicodedata.category(ch) == "Nd" and not ch.isascii()) else ch
                    for ch in t)
    return t


def _compact(s: str) -> str:
    """主體偵測用：移除空白／標點／符號，並把 USD 統一成「美元」。

    杜絕「美元，曝險」「美元；曝險」「美 元」「美元曝\n險」等分隔／夾字規避。
    """
    t = re.sub(r"(?i)usd", "美元", _norm(s))
    return re.sub(r"[^0-9\u4e00-\u9fff%]", "", t)


def _latin_cur(s: str) -> bool:
    """拉丁正規化幣別偵測：去非英數後比對概念集（U.S. dollar → usdollar、US-Dollar → usdollar）。"""
    flat = re.sub(r"[^a-z0-9]", "", s.lower())
    return any(tok in flat for tok in _CUR_LATIN)


# 舊版函式保留（回溯比對用；v12 判定路徑不再使用）
_CUR = r"(美元|美金|外幣|外匯|外币|外汇|美圆|美鈔|美钞|美刀|USD)"
_NOUN = (r"(曝險|曝险|暴險|暴险|部位|比重|佔比|占比|配置|資產|资产|風險|风险|水位|"
         r"布局|佈局|持有|持倉|持仓|餘額|余额|倉位|仓位|多頭|多头|空頭|空头|"
         r"比例|敞口|份额|份額|比率|头寸|頭寸|重倉|重仓|貨底|货底)")
_USD_SUBJ_RE = re.compile(_CUR + r".{0,6}?" + _NOUN, re.IGNORECASE)
_ACT = r"(加碼|加码|減碼|减码|減持|减持|增持|出清|歸零|归零|降低|提高|賣出|卖出|買進|买进|" \
      r"轉做|转做|轉往|转往|換成|换成|調節|调节|調整|调整|減|减|砍|轉|转|降)"
_USD_ACTION_RE = re.compile(
    _ACT + r".{0,3}?" + _CUR + r"|" + _CUR + r".{0,3}?" + _ACT, re.IGNORECASE)

_NEUTRAL = "（美元曝險目前為 🟡 僅顯示：政策門檻待 10 月戰略檢討，不觸發資產調整）"
_SENT = re.compile(r"[^。！!?\n]*[。！!?\n]?")
_MARKER_RE = re.compile(r"僅顯示|只顯示")
# canonical 行禁用「方向符號編碼」（第十三／十四輪 CIO）：`100%→0%`、`-100%`、`⇨ 0%`、`≥70%` 等。
# 第十四輪實證：只列舉 11 個箭頭仍不完備（⇨ ⇒ ➔ ➜ ⇢ ↦ ⇾ ↔ ⇄ ⤍ ⭢ ⬅ ⬈ ⟹ 🡒 全通關）
# → 改為「Unicode 區塊級封鎖 ＋ 符號字元封鎖」，不再逐字列舉。
# 區塊以 codepoint 建構（避免原始碼轉義被工具解析掉）：
#   U+2190–21FF 箭頭、U+27F0–27FF 補充箭頭A、U+2900–297F 補充箭頭B、
#   U+2B00–2BFF 雜項符號與箭頭、U+1F800–1F8FF 補充箭頭C
_ARROW_RANGES = ((0x2190, 0x21FF), (0x27F0, 0x27FF), (0x2900, 0x297F),
                 (0x2B00, 0x2BFF), (0x1F800, 0x1F8FF))
_ARROW_CHARS = "→←↑↓↗↘⇧⇩⟶➡⬆⬇⇒⇐⇔⇨⇦⭢⭠↔⇄⇢⇠↦⇾⇽⤍⤏🡒"
_CMP_CHARS = "≥≤＞＜≧≦≠＝=＋++-−–—‒―‐～〜~"
_CANON_BLOCK_RE = re.compile(
    "[" + "".join(chr(a) + "-" + chr(b) for a, b in _ARROW_RANGES)
    + re.escape(_ARROW_CHARS + _CMP_CHARS) + "]")
_ARROW_RE = _CANON_BLOCK_RE          # 回溯相容別名
# canonical 行的「字元白名單」（第十四輪 CIO 建議：不再用類別白名單＋有限黑名單）：
#   ASCII 只允許英數與非運算符標點；非 ASCII 只允許 指定 emoji、Po/Ps/Pe/Zs/Nd 類別與 _ALLOWED_VOCAB 漢字。
#   故 ⇨➔➜／≥／–／—／～／+／-／>／<／= 與「全數台幣」（全、數 不在詞彙集）全部出局。
_ALLOWED_ASCII_PUNCT = set(" .,;:()[]{}%$|'_\"!?/@#&*｜")
_ALLOWED_EMOJI = set("🟡🔴🟢⚪🟠🔵⚠✅❗❌")
_CANON_CATS = ("Po", "Ps", "Pe", "Zs", "Nd")
_SIGNED_NUM_RE = re.compile(r"[+\-−]\s*\d")
_PCT_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?\s*%")
_CN_NUM_RE = re.compile(r"[零〇一二三四五六七八九十百千萬億半]")
_NUM_RE = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?")
_CANON_ASCII_OK = {"usd", "advisory"}   # canonical 行內唯一允許的 ASCII 字母串
_SUBJ_RE = _BROAD_CUR_RE          # canonical 的「主體」＝任一廣義幣別主體
# canonical 行內仍不得出現方向／處置詞（第八輪 CIO：`美元曝險僅顯示，美元空頭布局。` 曾通關）。
# 注意：本表僅作用於「已含僅顯示標記」的 canonical 行；非 canonical 句一律違規，不經此表。
# `動用` 用否定後顧避開帳務事實用語「可動用」。
_DIRECTION_RE = re.compile(
    r"(布局|佈局|配置|避險|避险|(?<!可)動用|动用|持有|多頭|多头|空頭|空头|重倉|重仓|"
    r"減碼|加碼|提高|降低|調整|调节|調節|調高|調低|上調|下調|增持|減持|出清|歸零|"
    r"看多|看空|買進|賣出|加倉|减仓|減倉|轉|換|買|賣|增|減|降|停|砍|避)")


def _has_usd_subject(s: str) -> bool:
    return bool(_USD_SUBJ_RE.search(_compact(s)))


def _canon_pct_allowed(snap) -> set:
    """第十六輪 CIO 建議：把 canonical 的數字**綁定真值**。

    canonical 行內的百分比只允許是 snapshot 裡美元曝險監控實際存在的值
    （現值 70.5／門檻 60／各分項…）。「目標 0%」「目標台幣100%」「門檻 0%」等
    一律不在集合內 → 出局。集合推不出來時回空集合（fail-closed）。
    """
    if not isinstance(snap, dict):
        return set()
    vals = set()

    def _add(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.add(round(float(v), 1))

    m = snap.get("usd_exposure_monitor")
    # 2026-10-07 裁決②：政策門檻唯一來源（thresholds_2026_0915.美元曝險_pct）優先納入真值集合
    _pt = ((snap.get("thresholds_2026_0915") or snap.get("thresholds") or {})
           .get("美元曝險_pct") or {})
    for k in ("目標", "黃", "紅"):
        _add(_pt.get(k))
    if isinstance(m, dict):
        cur = m.get("current")
        if isinstance(cur, dict):
            for k in ("合計", "目標值", "門檻", "現值", "current", "threshold"):
                _add(cur.get(k))
        for k in ("threshold", "current_pct", "threshold_pct", "target_pct"):
            _add(m.get(k))
        ts = m.get("target_split")
        if isinstance(ts, dict):
            for k in ("台幣", "美金"):
                _add(ts.get(k))
    _add(snap.get("usd_exposure_pct"))
    _add(snap.get("usd_exposure_threshold"))
    return vals


def _canon_threshold(snap):
    """canonical 標記後的百分比**唯一允許值**＝snapshot 的美元曝險門檻（現 60）。

    第十六輪把百分比綁到真值集合（70.5／60／40），第十七輪再要求掛在「門檻」之下，
    但集合內還有台幣分項 40 與現值 70.5 → `門檻 40%`／`門檻 70.5%` 仍可通行。
    第十八輪 CIO：標記後數字必須**等於真門檻**，非僅屬於真值集合。取不到即 None（fail-closed）。
    """
    if not isinstance(snap, dict):
        return None
    m = snap.get("usd_exposure_monitor")
    if not isinstance(m, dict):
        return None
    cands = []
    # 2026-10-07 裁決②：政策門檻唯一來源 = thresholds.美元曝險_pct.目標（優先）
    cands.append(cap(snap))
    cur = m.get("current")
    if isinstance(cur, dict):
        cands.append(cur.get("目標值"))
        cands.append(cur.get("門檻"))
    cands.append(m.get("threshold"))
    for v in cands:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return round(float(v), 1)
    return None


def _canon_current(snap):
    """canonical 標記**前**百分比所允許的值／門檻所在維度的真值（現值 70.5）與門檻 60。

    第十九輪 CIO（A 案一併處理）：標記前現值槽只驗「∈ 真值集合」→ `美元曝險 40% 僅顯示`／
    `美元曝險 門檻 40% 僅顯示`（把台幣分項 40 搬到標記前）可通行。改為**逐槽綁值**：
    標記前百分比 ∈ {現值, 門檻}；標記後數字一律須掛「門檻」且等於門檻。取不到即 None（fail-closed）。
    """
    if not isinstance(snap, dict):
        return None
    vals = set()
    m = snap.get("usd_exposure_monitor")
    if isinstance(m, dict):
        cur = m.get("current")
        if isinstance(cur, dict):
            for k in ("合計", "現值", "current"):
                v = cur.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.add(round(float(v), 1))
    v = snap.get("usd_exposure_pct")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        vals.add(round(float(v), 1))
    return vals or None


def _canonical(s: str, snap=None) -> bool:
    """canonical 允許句＝(a) 含僅顯示／只顯示（或 advisory）標記 ＋ (b) 無方向／處置詞
    ＋ (c) 無箭頭／帶號數值 ＋ (d) 字元全在允許集內（純事實顯示行）。

    第十三輪 CIO 阻擋 2：`美元曝險僅顯示 100%→0%。`／`美元曝險僅顯示 -100%。` 因 `→`／`-`
    屬允許字元類別而通關 —— 以純符號編碼的目標位移不得偽裝成「僅顯示」。故 canonical 內
    禁用箭頭與帶號數字（現值呈現不需要這兩者）。
    """
    t = _norm(s)
    if not (_MARKER_RE.search(t) or "advisory" in t.lower()):
        return False
    if _CANON_BLOCK_RE.search(t) or _SIGNED_NUM_RE.search(t):
        return False
    # 第十五輪 CIO：白名單字元可拼出方向／目標詞（`美元曝險僅顯示目標 0%。` 因 目／標／底／線／達
    # 皆在詞彙集而通關）。CIO 指出此為「語意判別不可能」的邊界 —— 但顯示行有一條**結構事實**：
    # 現值必定在「僅顯示」標記之前（先有曝險數字，才談只顯示）；把數字放在標記之後者即為目標／方向。
    _subj = _SUBJ_RE.search(t)
    _mark = _MARKER_RE.search(t) or re.search(r"(?i)advisory", t)
    if _subj is not None and _mark is not None:
        if _mark.start() <= _subj.start():
            return False                                   # 標記先於主體 → 非本管線產出的顯示形
        if not _PCT_RE.search(t[_subj.start():_mark.start()]):
            return False                                   # 主體與標記之間沒有現值 → 非顯示行（如「僅顯示目標 0%」）
        if len(_PCT_RE.findall(t[_mark.end():])) > 1:
            return False                                   # 標記之後超過一個百分比 → 目標對／方向
    # 第十六輪 CIO 阻擋：現值槽可塞目標值（`美元曝險目標台幣100% 僅顯示（目前 70.5%）。`／
    # `美元曝險 70.5% 僅顯示 門檻 0%。`／`美元曝險 70.5% 僅顯示 零。`）—— 只驗「有百分比」與
    # 「標記後不超過一個百分比」攔不住。CIO 給的結構解＝**資料綁定**：canonical 行內百分比
    # 必須 ∈ snapshot 推導集合｛現值 70.5、門檻 60、分項…｝；集合為空即 fail-closed。
    # 另禁中文數字（`零`／`一半` 之類無法用百分比集合表達的目標值）。
    _thr = _canon_threshold(snap) if snap is not None else None
    _cur = _canon_current(snap) if snap is not None else None
    if snap is not None and (_thr is None or _cur is None):
        return False                       # 取不到真門檻／真現值 → fail-closed
    if snap is not None:
        # ①標記**前**的百分比：只允許該維度自己的真值（現值 70.5／門檻 60）
        _pre = t[:(_mark.start() if _mark is not None else len(t))]
        for _m in _PCT_RE.finditer(_pre):
            _v = round(float(_m.group().rstrip("%").strip()), 1)
            if not any(abs(_v - _a) < 0.06 for _a in _cur):
                return False               # 第十五～十九輪：現值槽必須等於真實現值（60≠70.5 亦出局）
        # ②標記**後**的數字：一律須掛「門檻」且等於真門檻（含不帶 % 的裸數字）
        _tail_flag = _mark is not None
        _tail = t[_mark.end():] if _tail_flag else ""
        for _m in _NUM_RE.finditer(_tail):
            _head = _tail[:_m.start()]
            _is_thr_slot = bool(re.search(r"門檻\s*$", _head))
            if not _is_thr_slot:
                # 第二十輪 CIO 阻擋 1：逗號／日期豁免原以「含逗號即豁免」實作 →
                # `門檻 40,0%`／`門檻 0,0%`／`門檻 40 月。` 全數通行。改為：只有在**非門檻槽**
                # 時才適用豁免，且千分位須為正規分組（`\d{1,3}(,\d{3})+`，如 `889,623`）。
                # 第二十一輪 CIO 阻擋 2：`0,000%。`／`40,000%。` 以分組＋`%` 冒充金額豁免通關；
                # 真值金額「889,623」不帶 `%` → 帶 `%` 者一律非金額。
                _g = _m.group()
                _nxt = _tail[_m.end():]
                _is_money = bool(re.fullmatch(r"\d{1,3}(?:,\d{3})+", _g)) and not _nxt.startswith("%")
                _is_date = bool(re.match(r"\s*(?:月|年|日|週|時|分)", _nxt))
                if _is_money or _is_date:
                    continue               # 千分位金額／日期成分（如「889,623」「10 月」）非目標值
                return False               # 標記後數字未掛在「門檻」之下 → 目標／維持語意
            # 第二十一輪 CIO 阻擋 3：門檻槽內的非正規千分位（`門檻 6,0%` 去逗號＝60 而放行，
            # 但輸出字形「6,0%」不是真門檻）→ 門檻槽只允許純十進位，不得含逗號。
            if "," in _m.group():
                return False
            _nv = round(float(_m.group().replace(",", "")), 1)
            if abs(_nv - _thr) >= 0.06:
                return False               # 非真門檻（如以台幣分項 40／現值 70.5／畸形千分位冒充）
    if _CN_NUM_RE.search(t):
        return False                       # 中文數字（零／一半…）不得作為目標值表達
    # 第二十輪 CIO 阻擋 2：canonical 行內英文／ASCII 方向詞完全通行（`美元曝險 70.5% 僅顯示 SELL。`
    # ／`cut USD exposure.`／`GO LONG USD.`／`switch to TWD.`）—— 卡片核心是「僅顯示」不得夾帶指令，
    # 只擋中文方向詞不夠。canonical 行內 ASCII 字母串只允許 `USD`（幣別主體）與 `advisory`（標記）。
    for _run in re.findall(r"[A-Za-z]+", t):
        if _run.lower() not in _CANON_ASCII_OK:
            return False
    if _DIRECTION_RE.search(t):          # 帶了僅顯示標記仍給方向／處置 → 不允許
        return False
    if re.search(r"目標|維持|(?<!現金)底線", t):   # 第十七輪：方向／維持語意（同 持有 之義）；
        return False                              # `現金底線` 為真值標籤，予以豁免
    t = _ADVISORY_TOKEN_RE.sub("", t)
    for ch in t:
        if ch in _ALLOWED_VOCAB or ch in _ALLOWED_EMOJI:
            continue
        if ch.isascii():
            if ch.isalnum() or ch in _ALLOWED_ASCII_PUNCT:
                continue
            return False                        # ASCII 的 < > = + - ~ 等比較／位移符號一律不允許
        if unicodedata.category(ch) in _CANON_CATS:
            continue                            # 中文標點／空白／數字（不含 Pd 破折號、Sm 運算符、So 符號）
        return False
    return True


def clause_violation(cand: str, strict: bool = True, snap=None) -> str:
    """句子是否違規；回傳原因（未違規回空字串）。strict 保留相容：兩種模式同判準。

    v12 契約：C1 先遮蔽真值名稱 → C2 遮蔽後仍含廣義幣別主體者，只有 canonical 行可通行。
    """
    if not cand:
        return ""
    m = _mask_data(_norm(cand), snap)     # C1
    if not (_BROAD_CUR_RE.search(m) or _BROAD_CUR_RE.search(_compact(m)) or _latin_cur(m)):
        return ""                         # 遮蔽後無廣義幣別主體 → 不在本卡範圍
    if snap is None:
        return ("缺 snapshot：canonical 真值綁定無法驗證（fail-closed）")
    if _canonical(m, snap):               # C2
        return ""
    return ("提及美元/外幣主體而未落於 canonical『僅顯示』敘述"
            "（advisory-only guard：僅允許真值名稱與 canonical 顯示行）")


def violations(text: str, snap, strict: bool = True) -> list:
    """回傳違規清單（advisory 時才檢查；非 advisory 一律回空）。判定單元＝句子。"""
    if not text or not is_advisory(snap):
        return []
    hits = []
    t = str(text).replace(_NEUTRAL, "（略）")
    for line in t.split("\n"):
        for sent in _SENT.findall(line):
            if not sent.strip():
                continue
            reason = clause_violation(sent, strict, snap)
            if reason:
                hits.append({"主體": "美元曝險", "動詞": reason,
                             "片段": sent.replace("\n", " ").strip()[:120]})
    return hits


def scrub(text: str, snap) -> tuple:
    """把違規「句子」整句換成 canonical 中性敘述；不含美元曝險主體的內容逐字保留。"""
    if not text or not is_advisory(snap):
        return text, []
    hits = violations(text, snap)
    if not hits:
        return text, []
    out = []
    for line in str(text).split("\n"):
        keep, inserted = [], False
        for sent in _SENT.findall(line):
            if sent and clause_violation(sent, True, snap):
                # 第十七輪 CIO 阻擋 2：原條件 `and _NEUTRAL not in line` 讓「行內已含中性敘述」
                # 的違規句逃過中和（hits>0 但 kept=True）。改為逐句處理：該行尚無中性敘述時插入
                # 一次，已有時直接移除違規句 —— 保證中和後零違規且不重複插入。
                if _NEUTRAL in line or inserted:
                    continue
                keep.append(_NEUTRAL)
                inserted = True
            else:
                keep.append(sent)
        out.append("".join(keep))
    return "\n".join(out), hits


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    base = Path(__file__).resolve().parent
    snap = json.loads((base / "snapshot.json").read_text(encoding="utf-8"))
    print("advisory_only =", is_advisory(snap))
    print("label        =", label(snap))
    print("prompt_block :\n" + (prompt_block(snap) or "（空：非 advisory）"))
    for s in ("美元曝險 70.5%（🟡 僅顯示）", "美元曝險 70.5%，建議逢彈減碼。",
              "營業部DAWHO外幣組合存款-美金 0", "科技 14.9% 貼 15% 上限，逢彈減碼美股。"):
        print(f"  scrub: {s!r} -> {scrub(s, snap)[0][:70]!r}")
    sys.exit(0)

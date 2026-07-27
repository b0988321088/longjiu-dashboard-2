#!/usr/bin/env python3
"""DS vs Gemini 費用比較"""
# Token 單價 (per 1M tokens)
ds_in_off, ds_out_off = 0.5, 1.0    # CNY 離峰
ds_in_peak, ds_out_peak = 1.0, 2.0  # CNY 尖峰
gm_in, gm_out = 2.45, 9.80           # TWD 無尖離峰
cny_to_twd = 4.3                    # 匯率

# 一次典型對話
for label, in_t, out_t in [("一次簡單問題", 2000, 500), ("一次完整分析", 10000, 3000), ("1小時密集討論", 100000, 20000)]:
    ds_off = (in_t * ds_in_off + out_t * ds_out_off) / 1e6 * cny_to_twd
    ds_peak = (in_t * ds_in_peak + out_t * ds_out_peak) / 1e6 * cny_to_twd
    gm = (in_t * gm_in + out_t * gm_out) / 1e6
    print(f"{label}:")
    print(f"  DS離峰 NT${ds_off:.4f}  |  DS尖峰 NT${ds_peak:.4f}  |  Gemini NT${gm:.4f}")
    print(f"  Gemini = DS離峰 {gm/ds_off:.1f}x  |  Gemini = DS尖峰 {gm/ds_peak:.1f}x")
    print()

# 月費比較
print("=" * 45)
print("月費比較（依7月實際用量推算）")
print("=" * 45)
ds_month = 200 * cny_to_twd  # ~NT$860
gm_month = 899
print(f"DS Flash 月費:     NT${ds_month:.0f}")
print(f"Gemini 7月實際:    NT${gm_month}")
print(f"Gemini/DS倍率:     {gm_month/ds_month:.1f}x")
print()
print("💡 結論：日常用DS離峰省錢，策略審查保留Gemini")
print("   經過優化(CIO改週一三)，月費可降至 ~NT$1,500")


import json, sys
sys.path.insert(0,"C:/Users/bot/Desktop/longjiu_system")
from allianz_sync import apply_policy_update
P="C:/Users/bot/Desktop/longjiu_system/snapshot.json"
snap=json.load(open(P,encoding="utf-8"))
bfunds={"NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息":244462,
 "NTDET0010 元大台灣卓越50":871663,
 "USDEQ3490 安聯收益成長基金-AM月收類股(美元)":476448,
 "USDEQ5700 M&G入息基金A(美元避險月配)F":630237,
 "USDEQ6730 貝萊德世界黃金基金A10美元(總報酬穩定配息)":133133}
print("B funds sum", sum(bfunds.values()))
apply_policy_update(snap,"b",total=2355943,funds=bfunds,source="安聯 App 11/19 13:43（B 逐檔 5 檔）",as_of="2026-11-19")
apply_policy_update(snap,"a",total=4851426,source="安聯 App 11/19 13:43（僅總值，逐檔待補）",as_of="2026-11-19")
json.dump(snap,open(P,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("A",snap.get("allianz_a_value"),"B",snap.get("allianz_b_value"),"AB",snap.get("allianz_ab_current_value"))
print("gapA",json.dumps(snap.get("allianz_a_detail_gap"),ensure_ascii=False))

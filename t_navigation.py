"""
t_navigation.py
龍九控股 — T+n 工作日导航规则（含 15:00 截止、假日扣除）
"""

from datetime import date, timedelta, datetime
from typing import Optional

# 2026 台湾国定/纪念日
HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 27), date(2026, 1, 28), date(2026, 1, 29), date(2026, 1, 30),
    date(2026, 2, 1),  date(2026, 2, 2),  date(2026, 2, 27), date(2026, 3, 1),
    date(2026, 4, 2),  date(2026, 4, 3),  date(2026, 4, 4),  date(2026, 4, 5),
    date(2026, 5, 1),
    date(2026, 6, 1),  date(2026, 6, 2),
    date(2026, 9, 27),
    date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12),
    date(2026, 12, 25),
}

CUTOFF_HOUR = 15
def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS_2026

def next_workday(from_date: date) -> date:
    d = from_date + timedelta(days=1)
    while not is_workday(d):
        d += timedelta(days=1)
    return d

def prev_workday(from_date: date) -> date:
    d = from_date - timedelta(days=1)
    while not is_workday(d):
        d -= timedelta(days=1)
    return d

def resolve_t_date(trade_date: date, trade_time: Optional[str] = None) -> date:
    """
    输入交易日期与时间，返回 T 日。
    15:00 前完成 = T 日 = trade_date（若为工作日）或下一个工作日。
    15:00 后 = 当作下一个工作日才算。
    """
    if trade_time:
        try:
            hh = int(trade_time.split(":")[0])
            if hh >= CUTOFF_HOUR:
                trade_date = next_workday(trade_date)
        except Exception:
            pass
    if not is_workday(trade_date):
        trade_date = next_workday(trade_date)
    return trade_date

def calc_ex_date(trade_date: date, trade_time: Optional[str] = None, t_plus: int = 4) -> date:
    """
    计算 T+n 后的基准日（取工作日）。
    """
    t = resolve_t_date(trade_date, trade_time)
    d = t
    added = 0
    while added < t_plus:
        d += timedelta(days=1)
        if is_workday(d):
            added += 1
    return d

def calc_deadline(ex_date: date, t_plus: int = 4) -> date:
    """
    从基准日倒推 T+n 最后申请日。
    """
    d = prev_workday(ex_date)
    for _ in range(t_plus - 1):
        d = prev_workday(d)
    return d

def smart_eta(trade_date: date, trade_time: Optional[str], ex_date: date, t_plus: int = 4, label: str = "") -> str:
    """
    综合判断是否赶得上基准日，回传人类可读提示。
    """
    deadline = calc_deadline(ex_date, t_plus)
    t = resolve_t_date(trade_date, trade_time)
    finish = calc_ex_date(trade_date, trade_time, t_plus)
    ok = finish <= ex_date
    return (
        f"⏰ {label}：T 日 = {t} | 最后申请日 = {deadline} | T+{t_plus} = {finish} | "
        f"基准日 = {ex_date} | {'✅ 可参与' if ok else '❌ 无法参与本期'}"
    )

if __name__ == "__main__":
    # 验证用户场景：QL18610694/QL18488224 昨晚 7/08 18:00 后转 M&G → T = 7/09
    print(smart_eta(date(2026,7,8), "18:00", date(2026,7,17), 4, "QL18610694/QL18488224 → M&G"))
    # FJ33 今天 7/09 下午3点前 转安联
    print(smart_eta(date(2026,7,9), "14:00", date(2026,7,14), 2, "FJ33 → FL65"))

"""Indonesian retail calendar features: Ramadan, Eid al-Fitr (Lebaran) and e-commerce mega-sales.

Ramadan moves ~11 days earlier every year, so a plain month-of-year seasonality cannot capture
it; the forecaster uses the share of days in each month that fall in Ramadan, in the two-week
pre-Eid shopping peak and in the post-Eid holiday week.
"""
from __future__ import annotations

import pandas as pd

# (first day of Ramadan, last day of Ramadan); Eid al-Fitr is the following day. Government dates.
RAMADAN = {
    2019: ("2019-05-06", "2019-06-04"), 2020: ("2020-04-24", "2020-05-23"), 2021: ("2021-04-13", "2021-05-12"),
    2022: ("2022-04-03", "2022-05-01"), 2023: ("2023-03-23", "2023-04-21"), 2024: ("2024-03-12", "2024-04-09"),
    2025: ("2025-03-01", "2025-03-30"), 2026: ("2026-02-18", "2026-03-19"), 2027: ("2027-02-08", "2027-03-09"),
    2028: ("2028-01-28", "2028-02-26"),
}
MEGA_SALE = {9: 0.5, 10: 0.5, 11: 1.0, 12: 1.0}  # 9.9, 10.10, 11.11 and 12.12 (Harbolnas)


def month_features(month: pd.Timestamp | str) -> dict:
    m = pd.Period(pd.Timestamp(month), freq="M")
    days = pd.date_range(m.start_time, m.end_time.normalize(), freq="D")
    ram = pre = post = 0
    for d in days:
        for start, end in RAMADAN.values():
            s, e = pd.Timestamp(start), pd.Timestamp(end)
            eid = e + pd.Timedelta(1, unit="D")
            if s <= d <= e:
                ram += 1
                if (eid - d).days <= 14:
                    pre += 1
            elif eid <= d <= eid + pd.Timedelta(6, unit="D"):
                post += 1
    n = len(days)
    return dict(month_of_year=m.month, days_in_month=n, ramadan_share=ram / n, pre_eid_share=pre / n,
                post_eid_share=post / n, mega_sale=MEGA_SALE.get(m.month, 0.0))


def calendar_frame(months) -> pd.DataFrame:
    rows = [dict(month=pd.Timestamp(m), **month_features(m)) for m in months]
    return pd.DataFrame(rows)


def eid_date(year: int) -> pd.Timestamp:
    return pd.Timestamp(RAMADAN[year][1]) + pd.Timedelta(1, unit="D")

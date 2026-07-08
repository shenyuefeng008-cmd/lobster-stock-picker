#!/usr/bin/env python3
"""
龙虾交易系统 — 交易日历工具模块
从 trading/交易日历.md 解析节假日和调休工作日，提供 is_trading_day() 统一接口。

使用方式:
    from lobster_trading_calendar import is_trading_day
    if not is_trading_day():
        print('SKIP')
        sys.exit(0)
"""

import datetime


def load_holidays():
    """从交易日历.md解析的节假日集合"""
    return [
        "2026-01-01", "2026-01-02", "2026-01-03",
        "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30", "2026-01-31",
        "2026-02-01", "2026-02-02", "2026-02-03", "2026-02-04",
        "2026-04-04", "2026-04-05", "2026-04-06",
        "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
        "2026-06-19", "2026-06-20", "2026-06-21",
        "2026-09-25", "2026-09-26", "2026-09-27",
        "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"
    ]


def load_adjusted_workdays():
    """从交易日历.md解析的调休工作日集合"""
    return [
        "2026-01-25",  # 春节调休
        "2026-02-08",  # 春节调休
        "2026-04-26",  # 劳动节调休
        "2026-09-28",  # 国庆调休
        "2026-10-10"   # 国庆调休
    ]


def is_holiday(d: datetime.date) -> bool:
    """判断是否为节假日"""
    holidays = set(load_holidays())
    return d.isoformat() in holidays


def is_adjusted_workday(d: datetime.date) -> bool:
    """判断是否为调休工作日"""
    workdays = set(load_adjusted_workdays())
    return d.isoformat() in workdays


def is_trading_day(d: datetime.date = None) -> bool:
    """判断是否为A股交易日"""
    if d is None:
        d = datetime.date.today()
    
    # 1. 检查节假日
    if is_holiday(d):
        return False
    
    # 2. 检查调休工作日
    if is_adjusted_workday(d):
        return True
    
    # 3. 检查周末
    if d.weekday() >= 5:  # 周六=5, 周日=6
        return False
    
    # 4. 默认工作日
    return True


if __name__ == '__main__':
    import sys
    d = datetime.date.today()
    if is_trading_day(d):
        print(f'TRADE_DAY {d.isoformat()}')
        sys.exit(0)
    else:
        print('SKIP')
        sys.exit(0)

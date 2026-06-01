"""
交易日判断模块
简单版：周一至周五为交易日，不考虑节假日
"""
import datetime

def is_trading_day(d):
    """
    判断是否为交易日
    Args:
        d: datetime.date 对象
    Returns:
        bool: True=交易日, False=非交易日
    """
    # 简单判断：周一到周五
    return d.weekday() < 5

def get_next_trading_day(d):
    """
    获取下一个交易日
    Args:
        d: datetime.date 对象
    Returns:
        datetime.date: 下一个交易日
    """
    next_day = d + datetime.timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += datetime.timedelta(days=1)
    return next_day

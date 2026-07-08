#!/usr/bin/env python3
"""龙虾系统数据获取助手 — 替代 westock-data + legulegu 的 Marvis 版本"""

import sys, json, subprocess
from datetime import datetime

def get_limit_up_pool():
    """获取今日涨停板列表（替代 westock-data sector pt02031283）"""
    try:
        import akshare as ak
        today = datetime.now().strftime('%Y%m%d')
        df = ak.stock_zt_pool_em(date=today)
        if df.empty:
            # 回退尝试上一交易日
            df = ak.stock_zt_pool_em(date='')
        for _, row in df.head(50).iterrows():
            fd = row.get('封板资金', 0) or 0
            print(f"{row['代码']} {row['名称']} 涨停价{row['最新价']:.2f} 封单{fd/1e8:.1f}亿 {row.get('首次封板时间','')} {row.get('连板数','')}连板")
    except Exception as e:
        print(f"STOCK_LIMIT_UP_ERROR: {e}")

def get_consecutive_limit_up():
    """获取连板股列表（涨停池中筛选连板）"""
    try:
        import akshare as ak
        today = datetime.now().strftime('%Y%m%d')
        df = ak.stock_zt_pool_em(date=today)
        if df.empty:
            df = ak.stock_zt_pool_em(date='')
        if df.empty:
            print("NO_DATA")
            return
        # 按连板数排序
        if '连板数' in df.columns:
            df = df.sort_values('连板数', ascending=False)
            for _, row in df.head(30).iterrows():
                lb = row.get('连板数', '?')
                print(f"{row['代码']} {row['名称']} {lb}连板 涨停价{row['最新价']:.2f}")
        else:
            # 无连板数字段，输出全部涨停
            for _, row in df.head(30).iterrows():
                print(f"{row['代码']} {row['名称']} 涨停价{row['最新价']:.2f} {row.get('首次封板时间','')}")

    except Exception as e:
        print(f"CONSECUTIVE_ERROR: {e}")

def get_market_sentiment():
    """获取涨跌家数（web_search 方案 — eastmoney API 代理不通时的替代）"""
    print("SENTIMENT_WEB_SEARCH_REQUIRED: 涨跌家数需要通过 web_search 获取，搜索关键词「A股 涨跌家数 今日」")
    print("数据格式参考: 792只上涨, 4676只下跌")

def get_sector_stocks(sector_name):
    """获取板块成份股涨跌（web_search 方案 — eastmoney API 代理不通时的替代）"""
    print(f"SECTOR_WEB_SEARCH_REQUIRED: 板块「{sector_name}」数据需要通过 web_search 获取")
    print(f"搜索关键词「{sector_name} 板块 涨跌 成分股 今日」")

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'limit-up':
        get_limit_up_pool()
    elif cmd == 'consecutive':
        get_consecutive_limit_up()
    elif cmd == 'sentiment':
        get_market_sentiment()
    elif cmd == 'sector' and len(sys.argv) > 2:
        get_sector_stocks(sys.argv[2])
    else:
        print("用法: python3 lob_data_helper.py [limit-up|consecutive|sentiment|sector <name>]")

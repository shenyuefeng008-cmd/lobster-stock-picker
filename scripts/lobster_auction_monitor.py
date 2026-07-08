#!/usr/bin/env python3
"""
龙虾竞价异动监控 v1.0 — thsdk 竞价异动采集
在 9:15-9:25 竞价时段运行，获取沪深竞价异动并进行筛选。

用法：
  python3 scripts/lobster_auction_monitor.py [--console-only]

数据源：thsdk.call_auction_anomaly("USHA") / call_auction_anomaly("USZA")
输出：trading/auction_anomaly.json
"""

import json
import sys
import datetime
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT_PATH = ROOT / 'trading' / 'auction_anomaly.json'

# 异动类型筛选关键词（匹配子串即可）
TARGET_TYPES = ['竞价抢筹', '大幅高开', '涨停试盘', '急速上涨']


def is_auction_time():
    """判断是否在竞价时段（9:15 - 9:25）"""
    now = datetime.datetime.now()
    hm = now.strftime('%H:%M')
    return '09:15' <= hm <= '09:25'


def call_auction_anomaly_fallback(market):
    """当 thsdk 不可用时的 fallback / 兜底实现。
    在实际部署环境中，thsdk 可能未安装；此处返回空列表并打印警告。
    """
    print(f'  ⚠️  thsdk 不可用，跳过 {market} 竞价异动采集', file=sys.stderr)
    return []


def fetch_auction_anomalies():
    """获取沪深竞价异动，返回合并后的异动列表。"""
    anomalies = []
    try:
        import thsdk
        for market in ['USHA', 'USZA']:
            try:
                result = thsdk.call_auction_anomaly(market)
                if result and isinstance(result, list):
                    for item in result:
                        item['_market'] = market
                    anomalies.extend(result)
                    print(f'  📡 thsdk {market}: {len(result)} 条异动', file=sys.stderr)
                else:
                    print(f'  ⚠️  thsdk {market}: 返回空或格式异常', file=sys.stderr)
            except Exception as e:
                print(f'  ⚠️  thsdk {market} 调用失败: {e}', file=sys.stderr)
    except ImportError:
        anomalies = call_auction_anomaly_fallback('USHA') + call_auction_anomaly_fallback('USZA')

    return anomalies


def filter_anomalies(anomalies):
    """筛选目标异动类型，返回匹配的异动列表。"""
    filtered = []
    for a in anomalies:
        a_type = a.get('type', a.get('异动类型', ''))
        if any(t in str(a_type) for t in TARGET_TYPES):
            filtered.append(a)
    return filtered


def save_output(anomalies):
    """保存到 trading/auction_anomaly.json"""
    output = {
        'timestamp': datetime.datetime.now().isoformat(),
        'market': 'A股',
        'filter_types': TARGET_TYPES,
        'total_raw': len(anomalies),
        'total_filtered': len(anomalies),
        'anomalies': anomalies,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'  ✅ 已写入 {OUT_PATH}', file=sys.stderr)


def print_top10(anomalies):
    """打印前10条到控制台"""
    display = anomalies[:10]
    if not display:
        print('\n📋 竞价异动：无符合条件的异动')
        return

    print(f'\n📋 竞价异动 TOP{len(display)}：')
    print(f'{"序号":<4} {"代码":<8} {"名称":<10} {"异动类型":<12} {"触发时间":<10} {"方向"}')
    print('-' * 60)
    for i, a in enumerate(display, 1):
        code = a.get('code', a.get('代码', ''))
        name = a.get('name', a.get('名称', ''))
        a_type = a.get('type', a.get('异动类型', ''))
        time_str = str(a.get('time', a.get('触发时间', '')))[:8]
        direction = a.get('direction', a.get('方向', ''))
        print(f'{i:<4} {str(code):<8} {str(name):<10} {str(a_type):<12} {time_str:<10} {str(direction)}')


def main():
    print(f'🦞 龙虾竞价异动监控 v1.0 | {datetime.datetime.now().strftime("%H:%M:%S")}')

    if not is_auction_time():
        print('⏸️  非竞价时段 (9:15-9:25)，跳过', file=sys.stderr)
        # 非竞价时段仍可手动运行，但不建议
        console_only = '--console-only' in sys.argv
        if not console_only:
            # 写入空文件标记
            save_output([])
        sys.exit(0)

    print('📥 获取竞价异动...')
    raw_anomalies = fetch_auction_anomalies()
    print(f'  原始异动: {len(raw_anomalies)} 条')

    filtered = filter_anomalies(raw_anomalies)
    print(f'  筛选后: {len(filtered)} 条 (类型: {", ".join(TARGET_TYPES)})')

    save_output(filtered)
    print_top10(filtered)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
龙虾分钟K线信号回测 v1.0 — thsdk 历史分钟K线回测
对持仓候选池标的回测量价异动信号的延续性。

用法：
  python3 scripts/lobster_backtest_minute.py [--days 30] [--code 000001]

数据源：thsdk.klines(code, interval="5m") 历史分钟K线
输出：reports/backtest_minute_signals.json + 控制台汇总
"""

import json
import sys
import datetime
import argparse
import os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / 'lobster-config.json'
OUT_DIR = ROOT / 'reports'


def load_backtest_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            pass
    bt = cfg.get('backtest', {}).get('minute_threshold', {})
    return {
        'volume_spike_ratio': bt.get('volume_spike_ratio', 2.0),
        'price_break_lookback': bt.get('price_break_lookback', 5),
        'hold_days': bt.get('hold_days', 3),
    }


def load_stock_codes():
    """回测标的：趋势池种子 + 持仓股"""
    codes = set()

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            stock_codes = cfg.get('trend_pool', {}).get('stock_codes', {})
            for code in stock_codes.values():
                codes.add(str(code))
        except Exception:
            pass

    pos_path = ROOT / 'trading' / '模拟持仓.json'
    if pos_path.exists():
        try:
            with open(pos_path) as f:
                pos = json.load(f)
            for p in pos.get('positions', []):
                codes.add(str(p.get('code', '')))
        except Exception:
            pass

    return list(codes)[:20]


def get_trade_dates(days=30):
    """往回推算交易日列表"""
    dates = []
    d = datetime.date.today()
    count = 0
    attempts = 0
    while count < days and attempts < days * 2:
        if d.weekday() < 5:
            dates.append(d.strftime('%Y%m%d'))
            count += 1
        d -= datetime.timedelta(days=1)
        attempts += 1
    return list(reversed(dates))


# ── thsdk 数据拉取 ──────────────────────────────────

def fetch_minute_klines(code, date_str, interval='5m'):
    """通过 thsdk.klines 拉取历史某日分钟K线。"""
    try:
        import thsdk
        raw = thsdk.klines(code, interval=interval, count=240, end_date=date_str)
        if not raw or not isinstance(raw, list):
            return None
        klines = []
        for k in raw:
            dt = str(k.get('datetime', k.get('time', '')))
            if date_str in dt.replace('-', ''):
                klines.append({
                    'time': dt,
                    'open': float(k.get('open', 0)),
                    'close': float(k.get('close', 0)),
                    'high': float(k.get('high', 0)),
                    'low': float(k.get('low', 0)),
                    'volume': float(k.get('volume', 0)),
                })
        return klines if klines else None
    except ImportError:
        return None
    except Exception as e:
        print(f'    ⚠️  klines({code}, {date_str}) 失败: {e}', file=sys.stderr)
        return None


def fetch_day_klines(code, date_str, lookback=10):
    """近N天日K线，用于计算 T+1/T+N 涨跌幅。"""
    try:
        import thsdk
        end_dt = datetime.datetime.strptime(date_str, '%Y%m%d') + datetime.timedelta(days=5)
        end_str = end_dt.strftime('%Y%m%d')
        raw = thsdk.klines(code, interval='day', count=lookback + 5, end_date=end_str)
        if not raw or not isinstance(raw, list):
            return None
        klines = []
        for k in raw:
            d = str(k.get('datetime', k.get('date', '')))[:10]
            klines.append({
                'date': d.replace('-', ''),
                'open': float(k.get('open', 0)),
                'close': float(k.get('close', 0)),
                'high': float(k.get('high', 0)),
                'low': float(k.get('low', 0)),
                'volume': float(k.get('volume', 0)),
            })
        return klines
    except ImportError:
        return None
    except Exception:
        return None


# ── 信号检测 ────────────────────────────────────────

def detect_volume_spike(klines, threshold=2.0):
    """检测成交量异动信号出现的时间点。返回列表 [(index, ratio)]。"""
    spikes = []
    window = 5
    for i in range(window, len(klines)):
        current_vol = klines[i]['volume']
        prev_vols = [klines[j]['volume'] for j in range(i - window, i)]
        avg_vol = sum(prev_vols) / len(prev_vols)
        if avg_vol > 0:
            ratio = current_vol / avg_vol
            if ratio >= threshold:
                spikes.append((i, ratio))
    return spikes


def detect_price_break(klines, lookback=5):
    """检测价格突破前N根K线最高价的时间点。返回列表 [(index, close, prev_high)]。"""
    breaks = []
    for i in range(lookback, len(klines)):
        prev_high = max(klines[j]['high'] for j in range(i - lookback, i))
        current_close = klines[i]['close']
        if current_close > prev_high and prev_high > 0:
            breaks.append((i, current_close, prev_high))
    return breaks


def calc_forward_performance(day_klines, signal_date_str, hold_days=3):
    """计算信号日后 T+1 / T+N 涨跌幅。"""
    result = {'t1_return': None, 't3_return': None, 't3_max_return': None}
    signal_idx = None
    for i, k in enumerate(day_klines):
        if k['date'] == signal_date_str:
            signal_idx = i
            break
    if signal_idx is None:
        return result

    signal_close = day_klines[signal_idx]['close']
    if signal_close <= 0:
        return result

    # T+1
    if signal_idx + 1 < len(day_klines):
        result['t1_return'] = round(
            (day_klines[signal_idx + 1]['close'] - signal_close) / signal_close * 100, 2
        )

    # T+N 最高
    end_idx = min(signal_idx + hold_days + 1, len(day_klines))
    if end_idx > signal_idx + 1:
        future_highs = [day_klines[j]['high'] for j in range(signal_idx + 1, end_idx)]
        future_closes = [day_klines[j]['close'] for j in range(signal_idx + 1, end_idx)]
        if future_highs:
            result['t3_max_return'] = round(
                (max(future_highs) - signal_close) / signal_close * 100, 2
            )
            result['t3_return'] = round(
                (future_closes[-1] - signal_close) / signal_close * 100, 2
            )

    return result


# ── 主回测 ──────────────────────────────────────────

def backtest_single_code(code, dates, config):
    """对单只股票回测所有日期。"""
    results_vol = []   # 成交量异动
    results_break = []  # 价格突破
    skipped = 0

    for date_str in dates:
        klines = fetch_minute_klines(code, date_str)
        if klines is None:
            skipped += 1
            continue

        day_klines = fetch_day_klines(code, date_str, lookback=config['hold_days'] + 2)
        if day_klines is None:
            skipped += 1
            continue

        # 量异动检测
        spikes = detect_volume_spike(klines, config['volume_spike_ratio'])
        for idx, ratio in spikes:
            fwd = calc_forward_performance(day_klines, date_str, config['hold_days'])
            results_vol.append({
                'date': date_str, 'code': code,
                'signal': 'volume_spike',
                'kline_time': klines[idx]['time'],
                'volume_ratio': round(ratio, 2),
                **fwd,
            })

        # 价格突破检测
        breaks = detect_price_break(klines, config['price_break_lookback'])
        for idx, close, prev_high in breaks:
            fwd = calc_forward_performance(day_klines, date_str, config['hold_days'])
            results_break.append({
                'date': date_str, 'code': code,
                'signal': 'price_break',
                'kline_time': klines[idx]['time'],
                'break_close': round(close, 2),
                'prev_high': round(prev_high, 2),
                **fwd,
            })

    return results_vol, results_break, skipped


def calc_stats(results, label):
    """计算统计指标。"""
    if not results:
        return {'label': label, 'total': 0}

    t1_rets = [r['t1_return'] for r in results if r.get('t1_return') is not None]
    t3_rets = [r['t3_return'] for r in results if r.get('t3_return') is not None]
    t3_maxs = [r['t3_max_return'] for r in results if r.get('t3_max_return') is not None]

    def avg(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0

    def win_rate(lst):
        return round(sum(1 for v in lst if v > 0) / len(lst) * 100, 1) if lst else 0

    return {
        'label': label,
        'total': len(results),
        't1_avg': avg(t1_rets),
        't1_win_rate': win_rate(t1_rets),
        't3_avg': avg(t3_rets),
        't3_win_rate': win_rate(t3_rets),
        't3_max_avg': avg(t3_maxs),
    }


def main():
    parser = argparse.ArgumentParser(description='龙虾分钟K线信号回测')
    parser.add_argument('--days', type=int, default=None, help='回测最近N个交易日')
    parser.add_argument('--code', type=str, default=None, help='指定单只股票代码')
    args = parser.parse_args()

    config = load_backtest_config()
    days = args.days or 30

    print(f'🦞 龙虾分钟K线信号回测 v1.0')
    print(f'   量异动阈值: ≥{config["volume_spike_ratio"]}x均量 / 价突破: 前{config["price_break_lookback"]}K高 / 持仓周期: {config["hold_days"]}天')

    codes = [args.code] if args.code else load_stock_codes()
    dates = get_trade_dates(days)
    print(f'📋 回测标的: {len(codes)} 只 | 日期范围: {dates[0]} ~ {dates[-1]} ({len(dates)}天)')

    all_vol = []
    all_break = []
    total_skipped = 0

    for code in codes:
        print(f'  {code} ...', file=sys.stderr)
        vol_r, break_r, skipped = backtest_single_code(code, dates, config)
        all_vol.extend(vol_r)
        all_break.extend(break_r)
        total_skipped += skipped

    # 统计
    stats_vol = calc_stats(all_vol, '成交量异动')
    stats_break = calc_stats(all_break, '价格突破')

    # 输出汇总
    print(f'\n📊 回测结果:')
    for s in [stats_vol, stats_break]:
        print(f'  {s["label"]}: {s["total"]}个信号')
        if s['total'] > 0:
            print(f'    T+1: 平均 {s["t1_avg"]}% | 胜率 {s["t1_win_rate"]}%')
            print(f'    T+{config["hold_days"]}: 平均 {s["t3_avg"]}% | 胜率 {s["t3_win_rate"]}% | 同期最高 {s["t3_max_avg"]}%')

    print(f'  数据不可用(跳过): {total_skipped} 天')

    # 写 JSON
    output = {
        'timestamp': datetime.datetime.now().isoformat(),
        'config': config,
        'date_range': f'{dates[0]}~{dates[-1]}',
        'codes_count': len(codes),
        'skipped': total_skipped,
        'summary': {
            'volume_spike': stats_vol,
            'price_break': stats_break,
        },
        'details': {
            'volume_spike': all_vol[:200],
            'price_break': all_break[:200],
        },
    }

    out_path = OUT_DIR / 'backtest_minute_signals.json'
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'✅ 已写入 {out_path}')


if __name__ == '__main__':
    main()

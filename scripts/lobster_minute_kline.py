#!/usr/bin/env python3
"""
龙虾分钟K线采集 v1.0 — thsdk 分钟K线 + 量价异动检测
对持仓股和候选池标的拉取 5 分钟 K 线，检测量价异动。

用法：
  python3 scripts/lobster_minute_kline.py

数据源：thsdk.klines(code, interval="5m", count=78)
输出：trading/minute_signals.json
"""

import json
import sys
import datetime
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT_PATH = ROOT / 'trading' / 'minute_signals.json'
POSITIONS_PATH = ROOT / 'trading' / '模拟持仓.json'
CANDIDATES_PATH = ROOT / 'trading' / 'watchlist_candidates.json'
CONFIG_PATH = ROOT / 'lobster-config.json'


def load_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            pass
    thsdk_cfg = cfg.get('thsdk', {})
    return {
        'volume_spike_threshold': thsdk_cfg.get('minute_volume_spike_threshold', 2.0),
        'price_break_periods': thsdk_cfg.get('minute_price_break_periods', 5),
    }


def load_target_codes():
    """从持仓 + 候选池 + watchlist_candidates 中提取标的代码列表。"""
    codes = set()

    # 持仓股
    if POSITIONS_PATH.exists():
        try:
            with open(POSITIONS_PATH) as f:
                pos_data = json.load(f)
            for p in pos_data.get('positions', []):
                code = p.get('code', '')
                if code:
                    codes.add(code)
        except Exception:
            pass

    # 候选池（premarket_candidates.json）
    pm_path = ROOT / 'trading' / 'premarket_candidates.json'
    if pm_path.exists():
        try:
            with open(pm_path) as f:
                pm_data = json.load(f)
            for dim_stocks in pm_data.get('candidates', {}).values():
                for s in dim_stocks:
                    code = str(s.get('代码', s.get('code', '')))
                    if code:
                        codes.add(code)
        except Exception:
            pass

    # watchlist_candidates.json
    if CANDIDATES_PATH.exists():
        try:
            with open(CANDIDATES_PATH) as f:
                cand_data = json.load(f)
            for dim_stocks in cand_data.get('candidates', {}).values():
                for s in dim_stocks:
                    code = str(s.get('代码', s.get('code', '')))
                    if code:
                        codes.add(code)
        except Exception:
            pass

    return list(codes)


def fetch_minute_klines_thssdk(code, interval='5m', count=78):
    """通过 thsdk 拉取分钟K线。如果 thsdk 不可用，返回空列表。"""
    try:
        import thsdk
        raw = thsdk.klines(code, interval=interval, count=count)
        if not raw or not isinstance(raw, list):
            return []
        # 统一字段格式
        klines = []
        for k in raw:
            klines.append({
                'time': str(k.get('datetime', k.get('time', ''))),
                'open': float(k.get('open', 0)),
                'close': float(k.get('close', 0)),
                'high': float(k.get('high', 0)),
                'low': float(k.get('low', 0)),
                'volume': float(k.get('volume', 0)),
            })
        return klines
    except ImportError:
        print(f'  ⚠️  thsdk 不可用，跳过 {code} 分钟K线', file=sys.stderr)
        return []
    except Exception as e:
        print(f'  ⚠️  {code} 分钟K线获取失败: {e}', file=sys.stderr)
        return []


def detect_volume_spike(klines, threshold=2.0):
    """
    检测成交量异动：当前K线成交量 > 近5根K线均量的 threshold 倍。
    返回 (is_spike, ratio) 
    """
    if len(klines) < 6:
        return False, 0
    current_vol = klines[-1]['volume']
    prev_volumes = [k['volume'] for k in klines[-6:-1]]
    avg_vol = sum(prev_volumes) / len(prev_volumes)
    if avg_vol == 0:
        return False, 0
    ratio = current_vol / avg_vol
    return ratio >= threshold, ratio


def detect_price_break(klines, periods=5):
    """
    检测价格突破前高：当前收盘价 > 前 periods 根K线中的最高价。
    返回 (is_break, prev_high, close)
    """
    if len(klines) < periods + 1:
        return False, 0, 0
    prev_klines = klines[-(periods + 1):-1]
    prev_high = max(k['high'] for k in prev_klines)
    current_close = klines[-1]['close']
    return current_close > prev_high, prev_high, current_close


def analyze_code(code, config):
    """对单个标的进行分钟K线分析，返回信号字典。"""
    klines = fetch_minute_klines_thssdk(code)
    if not klines:
        return {'code': code, 'has_klines': False, 'signals': []}

    signals = []
    threshold = config['volume_spike_threshold']
    break_periods = config['price_break_periods']

    # 成交量异动检测
    is_spike, vol_ratio = detect_volume_spike(klines, threshold)
    if is_spike:
        signals.append({
            'type': 'volume_spike',
            'description': f'成交量异动：当前量/5K均量 = {vol_ratio:.1f}x ≥ {threshold}x',
            'vol_ratio': round(vol_ratio, 2),
            'threshold': threshold,
        })

    # 价格突破检测
    is_break, prev_high, close = detect_price_break(klines, break_periods)
    if is_break:
        signals.append({
            'type': 'price_break',
            'description': f'价格突破：收盘{close:.2f} > 前{break_periods}K最高{prev_high:.2f}',
            'prev_high': round(prev_high, 2),
            'current_close': round(close, 2),
            'break_periods': break_periods,
        })

    return {
        'code': code,
        'has_klines': True,
        'kline_count': len(klines),
        'latest_close': round(klines[-1]['close'], 2) if klines else None,
        'signals': signals,
    }


def main():
    print(f'🦞 龙虾分钟K线采集 v1.0 | {datetime.datetime.now().strftime("%H:%M:%S")}')

    config = load_config()
    target_codes = load_target_codes()

    if not target_codes:
        print('⚠️  无持仓/候选池标的，跳过', file=sys.stderr)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = {
            'timestamp': datetime.datetime.now().isoformat(),
            'config': config,
            'target_count': 0,
            'analyzed_count': 0,
            'codes_with_signals': [],
            'details': {},
        }
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    print(f'📋 目标标的: {len(target_codes)} 只')
    print(f'📊 参数: 量异动阈值≥{config["volume_spike_threshold"]}x, 价格突破周期=前{config["price_break_periods"]}K')

    results = {}
    codes_with_signals = []
    for code in target_codes:
        result = analyze_code(code, config)
        results[code] = result
        if result['signals']:
            codes_with_signals.append(code)

    # 统计
    with_klines = sum(1 for r in results.values() if r['has_klines'])
    with_signals = len(codes_with_signals)

    output = {
        'timestamp': datetime.datetime.now().isoformat(),
        'config': config,
        'target_count': len(target_codes),
        'analyzed_count': with_klines,
        'codes_with_signals': codes_with_signals,
        'details': results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'✅ 已写入 {OUT_PATH}')

    # 控制台摘要
    print(f'\n📊 分钟K线信号汇总: {with_signals}/{with_klines} 只有信号')
    for code in codes_with_signals:
        detail = results[code]
        for sig in detail['signals']:
            print(f'  {code} | {sig["type"]}: {sig["description"]}')


if __name__ == '__main__':
    main()
